"""Join adjacent prose under the same hierarchy; preserve all parent provenance.

Reads the saved V2 view, not PDFs. Table rows remain intact and ambiguous column
paths are explicitly marked. No model calls or edits to the original sources.
"""
import argparse
from copy import deepcopy
from pathlib import Path
import re

import tiktoken

from _common import read_json, write_json, digest


def prepare(prepared, output):
    prepared, output = Path(prepared).resolve(strict=True), Path(output).resolve()
    if output.exists():
        raise ValueError('Use a new preparation directory')
    report = read_json(prepared / 'preparation_report.json')
    if digest(report['source']) != report['source_sha256']:
        raise ValueError('Original source changed')
    records = read_json(prepared / 'input/documents.json')
    sources = read_json(prepared / 'source_map.json')
    tokenizer = tiktoken.get_encoding('cl100k_base')
    grouped, pending = [], []

    def text_of(items):
        if len(items) == 1:
            return items[0]['text']
        prefix = items[0]['text'].split('\n\n', 1)[0]
        return prefix + '\n\n' + '\n\n'.join(i['text'].split('\n\n', 1)[-1] for i in items)

    def flush():
        if pending:
            grouped.append(list(pending))
            pending.clear()

    for record in records:
        prose = record['content_kind'] == 'text'
        # Preserve already meaningful paragraphs as individual extraction units.
        # Join small fragments/definitions rather than swallowing a whole intro
        # into a long passage that makes the model overlook its applications.
        small_neighbor = not pending or min(
            len(tokenizer.encode(pending[-1]['text'].split('\n\n', 1)[-1])),
            len(tokenizer.encode(record['text'].split('\n\n', 1)[-1]))) < 125
        body = record['text'].split('\n\n', 1)[-1]
        previous_body = pending[-1]['text'].split('\n\n', 1)[-1] if pending else ''
        new_definition = bool(re.match(r'^[A-Z][A-Za-z0-9 /(),-]{0,55}\.\s+[A-Z]', body))
        definition_boundary = previous_body.lower().startswith(('where ', 'and ')) and new_definition
        if (not prose or (pending and (pending[-1]['headings'] != record['headings']
                or definition_boundary or not small_neighbor or len(tokenizer.encode(text_of(pending + [record]))) > 900))):
            flush()
        if prose:
            pending.append(record)
        else:
            grouped.append([record])
    flush()
    new_records, new_sources = [], {}
    for group in grouped:
        first = deepcopy(group[0])
        parents = [r['id'] for r in group]
        text = text_of(group)
        ambiguous = False
        if first['content_kind'] == 'table':
            paths = re.findall(r'(?m)^(?:Cell|Unresolved merged cell[^\[]*) \[([^\]]+)\]', text)
            ambiguous = ('Unresolved merged cell' in text or any(
                path.count('↑') + path.count('↓') > 1 for path in paths))
            if ambiguous:
                text = text.replace('\n\n', '\nTABLE_METRIC_ALIGNMENT: ambiguous\n\n', 1)
        ident = first['id'] if len(group) == 1 else first['id'] + ':joined'
        first.update(id=ident, source_record_id=ident, text=text, preparation_contract='context-v3',
                     parent_record_ids=parents, table_metric_alignment_ambiguous=ambiguous,
                     docling_refs=list(dict.fromkeys(ref for r in group for ref in r['docling_refs'])))
        source = deepcopy(sources[parents[0]])
        source.update(record_id=ident, parent_record_ids=parents, content=text,
                      item_refs=first['docling_refs'], pages=sorted({p for i in parents for p in sources[i]['pages']}),
                      locations={ref: loc for i in parents for ref, loc in sources[i].get('locations', {}).items()},
                      table_metric_alignment_ambiguous=ambiguous)
        if len(tokenizer.encode(text)) >= 1024:
            raise ValueError('Joined context exceeds native no-split limit')
        new_records.append(first)
        new_sources[ident] = source
    if {p for r in new_records for p in r['parent_record_ids']} != set(sources):
        raise ValueError('Original prepared record omitted')
    write_json(output / 'input/documents.json', new_records)
    write_json(output / 'source_map.json', new_sources)
    write_json(output / 'headings.json', read_json(prepared / 'headings.json'))
    result = {**report, 'preparation_contract': 'context-v3', 'parent_preparation': str(prepared),
              'records': len(new_records), 'parent_records_accounted': len(sources),
              'joined_prose_records': sum(len(g) > 1 for g in grouped),
              'ambiguous_table_rows': sum(r['table_metric_alignment_ambiguous'] for r in new_records),
              'max_record_tokens': max(len(tokenizer.encode(r['text'])) for r in new_records),
              'output_directory': str(output)}
    write_json(output / 'preparation_report.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('prepared', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = prepare(args.prepared, args.output)
    print({k: result[k] for k in ['records', 'parent_records_accounted', 'joined_prose_records',
                                'ambiguous_table_rows', 'max_record_tokens']})
