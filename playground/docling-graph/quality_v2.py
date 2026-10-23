"""Conservative source checks and deterministic adapters, not a truth oracle."""
from collections import Counter
import copy
import re

from research_schema_v2 import CellEvidence, Evidence, Measurement, MethodConfiguration, Metric
from source_index import metric_name, normalized


def identity_name(value):
    return normalized(re.sub(r"[†‡]", "", value)).strip()


def normalize_records(paper):
    """Normalize formatting only. Preserve configurations and log every change."""
    changes = []
    metric_lookup = {}

    def visit(x):
        if hasattr(type(x), "model_fields"):
            if type(x).__name__ == "Metric":
                old = x.name
                x.name = metric_name(x.name)
                if old != x.name:
                    changes.append({"type": "metric_name", "from": old, "to": x.name})
                key = identity_name(x.name)
                if key in metric_lookup:
                    x.name = metric_lookup[key]
                else:
                    metric_lookup[key] = x.name
            if type(x).__name__ == "Method":
                backbone_names = {identity_name(m.name) for m in x.built_on}
                x.components = [m for m in x.components if identity_name(m.name) not in backbone_names]
            for field in type(x).model_fields:
                visit(getattr(x, field))
        elif isinstance(x, list):
            for value in x:
                visit(value)
    result = copy.deepcopy(paper)
    visit(result)
    # Direct extraction may put complete records in reference fields while
    # leaving their root catalogs empty. Preserve those genuine records.
    catalogs={"Method":("methods",{}),"Dataset":("datasets",{}),"Concept":("concepts",{}),"Metric":("metrics",{}),"MethodConfiguration":("configurations",{})}
    def collect(x):
        if hasattr(type(x),'model_fields'):
            kind=type(x).__name__
            if kind in catalogs:
                _,items=catalogs[kind]
                key=(identity_name(x.name),identity_name(x.experiment_name)) if kind=='MethodConfiguration' else identity_name(x.name)
                if key not in items:items[key]=copy.deepcopy(x)
                else:
                    target=items[key]
                    for field in type(x).model_fields:
                        old,new=getattr(target,field),getattr(x,field)
                        if (not old or old=='unknown') and new:setattr(target,field,copy.deepcopy(new))
            for field in type(x).model_fields:collect(getattr(x,field))
        elif isinstance(x,list):
            for item in x:collect(item)
    collect(result)
    for _,(field,items) in catalogs.items():
        original=len(getattr(result,field));setattr(result,field,list(items.values()))
        if len(items)!=original:changes.append({'type':'catalog_recovery','catalog':field,'before':original,'after':len(items)})
    return result, changes


def add_table_measurements(paper, source):
    """Reuse existing Docling cell/context indexing; never infer numeric splits."""
    log = {"added": 0, "unresolved": [], "table_assignments": [], "aliases": []}
    for experiment in paper.experiments:
        if experiment.measurements:
            log["unresolved"].append({"experiment":experiment.name,"reason":"model_measurements_replaced_by_source_cell_assignments","count":len(experiment.measurements)})
        experiment.measurements = []
    metrics = {identity_name(m.name): m for m in paper.metrics}
    methods = {identity_name(m.name): m for m in paper.methods}
    proposed = {identity_name(m.name): m for m in paper.introduced_methods}
    if not proposed:
        proposed = {k:m for k,m in methods.items() if m.role == "proposed"}
    for table in [u for u in source.units.values() if u.kind == "table"]:
        label = source.table_label(table)
        experiments = [e for e in paper.experiments if any(identity_name(t) == identity_name(label) for t in e.table_labels)]
        cells = [source.units[x] for x in table.context.get("cells", [])]
        numeric = [u for u in cells if u.cell and not (u.cell.column_header or u.cell.row_header or u.cell.row_section) and re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?",u.text.strip())]
        if len(experiments) != 1:
            log["unresolved"].append({"table":label,"reason":"table_experiment_assignment_not_unique","candidates":[e.name for e in experiments]})
            continue
        experiment = experiments[0]
        for ref in table.context.get('captions',[]):
            if not any(e.source_ref==ref for e in experiment.evidence):
                experiment.evidence.append(Evidence(quote=source.units[ref].text,source_ref=ref))
        ambiguous = [u for u in cells if "multiple_numeric_values" in u.issues or "spanning_data_cell" in u.issues]
        if ambiguous:
            log["unresolved"].append({"table":label,"reason":"ambiguous_table_cells","refs":[u.evidence_id for u in ambiguous],"skipped_numeric_cells":len(numeric)})
            continue
        log["table_assignments"].append({"table":label,"experiment":experiment.name,"status":"model_assigned_table_context"})
        for unit in numeric:
            rows = list(dict.fromkeys(unit.context.get("row_headers", []) + unit.context.get("row_labels", [])))
            rows = [source.units[r] for r in rows if source.units[r].cell.col_start == 0]
            headers = [source.units[r] for r in unit.context.get("column_headers", [])]
            if not rows or not headers:
                log["unresolved"].append({"cell":unit.evidence_id,"reason":"missing_row_or_column_context"}); continue
            # The most specific (last) header must cover exactly this column.
            level = max(u.cell.row_end for u in headers)
            leaf = [u for u in headers if u.cell.row_end == level]
            if len(leaf) != 1 or leaf[0].cell.col_end - leaf[0].cell.col_start != 1 or len(rows) != 1:
                log["unresolved"].append({"cell":unit.evidence_id,"reason":"non_unique_leaf_header_or_row"}); continue
            row = rows[0].text.strip()
            column = metric_name(leaf[0].text)
            metric = metrics.get(identity_name(column))
            if metric is None:
                # A source-reported table heading is sufficient to create an identity-only metric.
                if not column or re.search(r"\d.*\d",column):
                    log["unresolved"].append({"cell":unit.evidence_id,"reason":"invalid_metric_header"});continue
                metric = Metric(name=column, direction="lower" if "↓" in leaf[0].text else "higher" if "↑" in leaf[0].text else "unspecified")
                paper.metrics.append(metric); metrics[identity_name(column)] = metric
            configs = [c for c in paper.configurations if identity_name(c.experiment_name) == identity_name(experiment.name) and identity_name(c.name) == identity_name(row)]
            if not configs:
                # Match source row names to catalog methods, never to an invented algorithm.
                method = methods.get(identity_name(row))
                if method is None and identity_name(row) in {"ours","full model (ours)"} and len(proposed) == 1:
                    method = next(iter(proposed.values()))
                    log["aliases"].append({"row":row,"method":method.name,"experiment":experiment.name,"reason":"unique proposed method; source table row"})
                if method:
                    config = MethodConfiguration(name=row,experiment_name=experiment.name,method=copy.deepcopy(method),conditions=experiment.conditions)
                    paper.configurations.append(config); configs=[config]
            if len(configs) != 1:
                log["unresolved"].append({"cell":unit.evidence_id,"reason":"configuration_not_unique","row":row,"experiment":experiment.name});continue
            config = configs[0]
            for row_unit in rows:
                if not any(ev.source_ref==row_unit.evidence_id for ev in config.evidence):
                    config.evidence.append(Evidence(quote=row_unit.text,source_ref=row_unit.evidence_id))
            if not any(identity_name(c.name)==identity_name(config.name) and identity_name(c.experiment_name)==identity_name(config.experiment_name) for c in experiment.configurations):
                experiment.configurations.append(copy.deepcopy(config))
            key = (label,row,column,experiment.name)
            if any((m.table_label,m.row_label,m.column_label,m.experiment_name)==key for m in experiment.measurements):
                continue
            experiment.measurements.append(Measurement(table_label=label,row_label=row,column_label=column,
                experiment_name=experiment.name,reported_value=unit.text.strip(),metric=copy.deepcopy(metric),
                configuration=copy.deepcopy(config),unit=metric.unit,reported_multiplier=metric.reported_multiplier,
                cell_evidence=CellEvidence(cell_ref=unit.evidence_id,header_refs=[h.evidence_id for h in headers],
                                          row_refs=[r.evidence_id for r in rows],caption_refs=unit.context.get("captions",[]))))
            log["added"] += 1
    return paper, log


PATTERNS = {
    "BUILT_ON": ("Method","Method"), "USES_COMPONENT": ("Method","Method"),
    "USES_CONCEPT": ("Method","Concept"), "TRAINED_ON": ("Method","Dataset"),
    "CONFIGURATION_OF": ("MethodConfiguration","Method"), "EVALUATES": ("Experiment","MethodConfiguration"),
    "EVALUATED_ON": ("Experiment","Dataset"), "REPORTS_MEASUREMENT": ("Experiment","Measurement"),
    "USES_METRIC": ("Measurement","Metric"), "FOR_CONFIGURATION": ("Measurement","MethodConfiguration"),
    "REPORTS": (None,"Finding"), "HAS_LIMITATION": ("ResearchPaper","Finding"),
}


def assess_graph(graph_data, source):
    """Filter structural failures; expose exact evidence without claiming truth."""
    result = copy.deepcopy(graph_data)
    nodes = {n["id"]:n for n in result["nodes"]}
    metrics = {identity_name(n.get("name","")) for n in nodes.values() if n["label"] == "Metric"}
    datasets = {identity_name(n.get("name","")) for n in nodes.values() if n["label"] == "Dataset"}
    node_ledger = {}
    for n in nodes.values():
        anchors = []
        for ev in n.get("evidence",[]) or []:
            anchors.extend(source.locate(ev.get("quote",""),ev.get("source_ref","")))
        anchors = list({a["ref"]:a for a in anchors}.values())
        linkage = "quote_match" if anchors else "unresolved"
        if not anchors and n['label']=='Finding':
            anchors=source.locate(n.get('statement',''))
            if anchors:linkage='exact_statement_match'
        if not anchors and n["label"] in {"Method","Dataset","Concept","Metric"} and n.get("name"):
            # Presence supports the entity mention only, not its description or edges.
            pattern=r"(?<!\w)"+re.escape(normalized(n["name"]))+r"(?!\w)"
            anchors=[source.anchor(u.evidence_id) for u in source.units.values() if re.search(pattern,normalized(u.text))]
            linkage="name_match_only" if anchors else "unresolved"
        invalid = n["label"] == "Concept" and identity_name(n.get("name","")) in metrics
        invalid |= n["label"] == "Method" and identity_name(n.get("name","")) in datasets
        if n["label"] == "Method" and re.match(r"^(quantitative comparison|ablation study|evaluation on)\b",n.get("name",""),re.I):
            invalid = True
        if n["label"] == "Measurement":
            ce = n.get("cell_evidence") or {}
            ref = ce.get("cell_ref")
            unit = source.units.get(ref)
            valid = unit is not None and unit.kind == "table_cell" and unit.text.strip() == n.get("reported_value") and not any(x in unit.issues for x in ["multiple_numeric_values","spanning_data_cell"])
            if valid:
                expected_headers=unit.context.get("column_headers",[])
                headers=[source.units[r] for r in expected_headers]
                leaf=[h for h in headers if h.cell.row_end==max(x.cell.row_end for x in headers)] if headers else []
                row_ids=list(dict.fromkeys(unit.context.get("row_headers",[])+unit.context.get("row_labels",[])))
                rows=[source.units[r] for r in row_ids if source.units[r].cell.col_start==0]
                valid=(len(leaf)==1 and leaf[0].cell.col_end-leaf[0].cell.col_start==1 and len(rows)==1
                       and metric_name(leaf[0].text)==n.get("column_label") and rows[0].text.strip()==n.get("row_label")
                       and set(ce.get("header_refs",[]))==set(expected_headers)
                       and set(ce.get("row_refs",[]))=={r.evidence_id for r in rows}
                       and n.get("table_label")==source.table_label(source.units[unit.item_ref]))
            if valid:
                anchors = [source.anchor(r) for r in [ref,*ce.get("header_refs",[]),*ce.get("row_refs",[]),*ce.get("caption_refs",[])] if r in source.units]
                linkage="source_cell_assignment"
            invalid |= not valid
        status = "rejected" if invalid else "source_linked" if anchors else "needs_review"
        n["support_status"] = status
        n["linkage_type"] = linkage
        n["source_refs"] = [a["ref"] for a in anchors]
        n["pages"] = sorted({l["page_no"] for a in anchors for l in a["locations"]})
        node_ledger[n["id"]] = {"status":status,"linkage_type":linkage,"anchors":anchors,"note":"Exact source linkage is not independent semantic verification; name-only matches do not ground descriptions."}
    edges = []
    for e in result["edges"]:
        s,t=nodes[e["source"]],nodes[e["target"]]
        reason="source_support_not_resolved";status="needs_review"
        expected=PATTERNS.get(e.get("label"))
        refs=list(dict.fromkeys(s.get("source_refs",[])+t.get("source_refs",[])))
        if s["support_status"] == "rejected" or t["support_status"] == "rejected" or (expected and ((expected[0] and s["label"]!=expected[0]) or t["label"]!=expected[1])):
            status="rejected";reason="invalid_entity_type_or_relationship_pattern"
        elif 'relationship_evidence' in e:
            # A relation-specific quotation must pass its own checks. Never
            # replace a failed quote with endpoint co-occurrence elsewhere.
            from relationship_pass import validate_relationship
            proposal={'subject':{'name':s.get('name',''),'kind':s['label']},
                      'predicate':e['label'],'object':{'name':t.get('name',''),'kind':t['label']},
                      'evidence':e['relationship_evidence'],
                      'explanation':'; '.join(e.get('relationship_explanations',[])) or 'Model-proposed relation'}
            checked=validate_relationship(proposal,source,set(source.units))
            if checked['accepted']:
                status='source_linked';reason='exact_relation_quotations_and_lexical_checks; semantic_entailment_not_independently_verified'
                refs=sorted({ev['source_ref'] for ev in e['relationship_evidence']})
            else:
                status='rejected';reason='; '.join(checked['reasons'])
        elif s["label"] == "Measurement" or t["label"] == "Measurement":
            measurement = s if s["label"] == "Measurement" else t
            if measurement["support_status"] == "source_linked":
                assignment_valid=True
                if e['label']=='USES_METRIC':assignment_valid=identity_name(t.get('name',''))==identity_name(measurement['column_label'])
                elif e['label']=='FOR_CONFIGURATION':assignment_valid=identity_name(t.get('name',''))==identity_name(measurement['row_label']) and t.get('experiment_name')==measurement['experiment_name']
                elif e['label']=='REPORTS_MEASUREMENT':assignment_valid=s.get('name')==measurement['experiment_name']
                status="cell_grounded" if assignment_valid else "rejected"
                reason="exact_value_and_source_cell_context; experiment_assignment_is_model_extracted" if assignment_valid else "measurement_relationship_context_mismatch"
        elif s["label"] == "ResearchPaper" and t.get("source_refs"):
            status="source_linked";reason="paper_record_and_exact_supporting_passage"
        elif e['label']=='CONFIGURATION_OF' and s.get('source_refs'):
            row=identity_name(s.get('name',''));method=identity_name(t.get('name',''))
            proposed=[n for n in nodes.values() if n['label']=='Method' and n.get('role')=='proposed']
            if row==method or (len(proposed)==1 and proposed[0]['id']==t['id'] and (row in {'ours','full model (ours)'} or row.startswith(('w/o ','w/ ','ours (')))):
                status='source_linked';reason='source_row_and_within_paper_method_identity; configuration_scope_is_model_extracted'
        elif e['label']=='EVALUATES' and t.get('experiment_name')==s.get('name') and t.get('source_refs') and s.get('source_refs'):
            status='source_linked';reason='source_table_row_and_caption; experiment_assignment_is_model_extracted'
        elif s["label"] == "Method":
            target=normalized(t.get("name",""))
            relevant=[r for r in s.get("source_refs",[]) if target and target in normalized(source.units[r].text)]
            cues={"BUILT_ON":r"build|backbone|initializ|fine[\s-]*tun|finetun|instruction[\s-]*tun", "TRAINED_ON":r"train", "USES_COMPONENT":r"us[ei]|obtain|extract|encoder", "USES_CONCEPT":r"condition|attention|generat|context|represent|inject"}
            relevant=[r for r in relevant if re.search(cues.get(e["label"],r"(?!)"),normalized(source.units[r].text))]
            if relevant:
                status="source_linked";reason="target_and_relationship_cue_in_source_passage; semantic_review_not_claimed";refs=relevant
        elif s.get("source_refs") and t.get("source_refs"):
            shared=set(s["source_refs"]) & set(t["source_refs"])
            if shared:
                status="source_linked";reason="shared_source_passage; semantic_review_not_claimed";refs=sorted(shared)
        e.update(support_status=status,support_reason=reason,source_refs=refs if status != "needs_review" else [])
        edges.append(e)
    result["edges"]=edges
    usable_edges=[e for e in edges if e["support_status"] in {"source_linked","cell_grounded"}]
    used={v for e in usable_edges for v in [e["source"],e["target"]]}
    usable={"nodes":[n for n in result["nodes"] if n["id"] in used and n["support_status"]!="rejected"],"edges":usable_edges}
    return result, usable, {"nodes":node_ledger,"edges":edges}, {"node_statuses":dict(Counter(n["support_status"] for n in result["nodes"])),"edge_statuses":dict(Counter(e["support_status"] for e in edges)),"note":"Usable means source-linked candidate context, not independent factual verification. Answers must use source passages."}
