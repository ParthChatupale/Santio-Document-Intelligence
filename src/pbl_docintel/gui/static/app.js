import {getDocument, GlobalWorkerOptions, TextLayer} from './vendor/pdf.mjs?v=6.4.299';

GlobalWorkerOptions.workerSrc = '/static/vendor/pdf.worker.mjs?v=6.4.299';
const $ = id => document.getElementById(id);
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const readable = value => String(value || 'Not recorded').replaceAll('_', ' ');
const roles = {experiment_comparison_seed:'Comparison seed', integration_stress_test:'Ingestion test', parser_reference:'Parser reference'};
const categories = {results:'Results',table:'Tables',picture:'Pictures',formula:'Equations',text:'Text'};
const exportTypes = {
  evidence:['Evidence JSON','Indexed items, source locations and extraction issues'],
  docling:['Original Docling JSON','Unchanged conversion output'],
  results:['Result JSON','Provisional annotations, conditions and source links'],
  csv:['Result CSV','Reported values with evidence IDs, checks and review status'],
  markdown:['Result Markdown','Readable provisional result table'],
  checks:['Attribution checks JSON','Current check findings; not scientific verification'],
  rag:['RAG JSONL','Source-linked retrieval chunks from the Python library']
};
const issueNames = {
  multiple_numeric_values:'Several numeric values occupy one extracted cell.',
  numeric_value_unresolved:'No single numeric value has been assigned.',
  method_row_label_inferred:'The method label is inferred from the first column.',
  metric_header_not_unambiguous:'The metric header does not unambiguously identify this value.',
  metric_requires_table_layout_review:'Inspect the original table to resolve the metric columns.',
  annotation_requests_review:'The provisional annotation explicitly requests review.',
  empty_extracted_text:'This detected region has no extracted text.',
  empty_table_structure:'A table region was detected, but no cell structure was extracted.',
  cell_location_not_resolved:'The source location is table-level; an exact cell box is unavailable.',
  spanning_data_cell:'This extracted data cell spans more than one row or column.',
  missing_page_provenance:'No page location is available for this evidence.'
};
const params = new URLSearchParams(location.search);
const state = {papers:[], data:null, paper:params.get('paper'), page:1, mode:'inspect', category:'results',
  selection:null, record:null, pdf:null, pageProxy:null, viewport:null, epoch:0, renderSerial:0,
  renderTask:null, textTask:null, loadTask:null, controller:null};
let restoring = null;
try { restoring = JSON.parse(localStorage.getItem('research-workspace') || 'null'); } catch { /* Optional storage. */ }
const endpoint = suffix => `/api/papers/${encodeURIComponent(state.paper)}${suffix}`;
const units = () => state.data?.units || {};
const records = () => state.data?.records || [];
const checkFor = id => state.data?.checks.find(c => c.result_id === id);
const flagged = record => { const c=checkFor(record.result_id); return c && c.outcome !== 'evidence_checks_passed'; };
const unitCategory = unit => unit.kind === 'text' && unit.label === 'formula' ? 'formula' : unit.kind;
const field = (name,value) => `<div class="field"><span class="field-label">${escape(name)}</span><span class="field-value">${escape(value ?? 'Not recorded')}</span></div>`;
const pagesLabel = unit => { const pages=[...new Set(unit.locations.map(l=>l.page_no))]; return pages.length ? `Page ${pages.join(', ')}` : 'Location unavailable'; };
function unitTitle(unit) {
  if (unit.kind === 'table') {
    const caption=(unit.context.captions || []).map(id=>units()[id]?.text).join(' ');
    return caption || `Detected table ${Number(unit.item_ref.split('/').pop())+1}`;
  }
  if (unit.kind === 'picture') {
    const caption=(unit.context.captions || []).map(id=>units()[id]?.text).join(' ');
    return caption || `Detected picture ${Number(unit.item_ref.split('/').pop())+1}`;
  }
  if (unit.label === 'formula' && !unit.text.trim()) return 'Formula region · transcription unavailable';
  return unit.text.trim() || readable(unit.label);
}
function recordLabel(record) { return `${record.method.normalized || record.method.reported} · ${record.benchmark.dataset.reported} · ${record.metric.name.reported} · ${record.value.raw}`; }
function error(message) { $('app-error').textContent=message; $('app-error').hidden=!message; }
function status(message) { $('app-status').textContent=message; }
function controls(enabled) {
  ['page-prev','page-next','page-number','zoom'].forEach(id=>$(id).disabled=!enabled);
  if (enabled && state.pdf) { $('page-prev').disabled=state.page<=1; $('page-next').disabled=state.page>=state.pdf.numPages; }
}
function remember() {
  if (!state.data) return;
  const value={paper:state.paper,document:state.data.document?.document_id,page:state.page,category:state.category,selection:state.selection,record:state.record};
  try {localStorage.setItem('research-workspace',JSON.stringify(value));} catch { /* Work without storage. */ }
  const query=new URLSearchParams({paper:state.paper,page:String(state.page)});
  if (state.record) query.set('result',state.record);
  history.replaceState(null,'',`?${query}`);
}
function renderLibrary() {
  $('paper-count').textContent=state.papers.length;
  $('papers').innerHTML=state.papers.map(p=>`<button class="paper" data-paper="${escape(p.paper_id)}" aria-pressed="${p.paper_id===state.paper}" title="${escape(p.title)}"><span class="paper-title">${escape(p.title)}</span><span class="paper-subtitle">${escape(roles[p.role] || readable(p.role))} · ${p.processed?'Processed':'Not indexed'}${p.source_available?'':' · Source missing'}</span></button>`).join('');
  $('paper-picker').innerHTML=state.papers.map(p=>`<option value="${escape(p.paper_id)}" ${p.paper_id===state.paper?'selected':''}>${escape(p.title)}</option>`).join('');
}
function renderPicker() {
  const all=Object.values(units());
  $('evidence-category').disabled=!state.data?.document;
  $('evidence-category').innerHTML=Object.entries(categories).map(([key,label])=>{
    const count=key==='results' ? (state.mode==='review'?records().filter(flagged):records()).length : all.filter(u=>unitCategory(u)===key).length;
    return `<option value="${key}" ${key===state.category?'selected':''}>${label} (${count})</option>`;
  }).join('');
  const options=state.category==='results' ? (state.mode==='review'?records().filter(flagged):records()).map(r=>({id:r.result_id,label:recordLabel(r)})) : all.filter(u=>unitCategory(u)===state.category).map(u=>({id:u.evidence_id,label:`${pagesLabel(u)} · ${unitTitle(u).slice(0,140)}`}));
  const active=state.category==='results'?state.record:state.selection;
  $('evidence-picker').innerHTML=options.length ? `<option value="">Select evidence…</option>${options.map(o=>`<option value="${escape(o.id)}" ${o.id===active?'selected':''}>${escape(o.label)}</option>`).join('')}` : `<option value="">${state.category==='results'?'No result annotations available':'No regions in this category'}</option>`;
  $('evidence-picker').disabled=!options.length;
}
function sourceButton(id,label) {
  const unit=units()[id];
  if (!unit) return '';
  return `<button class="source-link" data-evidence="${escape(id)}">${escape(label || unitTitle(unit).slice(0,170))}<span>${escape(pagesLabel(unit))} · ${escape(readable(unit.label))}</span></button>`;
}
function renderDetail() {
  const unit=units()[state.selection], record=records().find(r=>r.result_id===state.record);
  $('inspector-title').textContent=state.mode==='review'?'Review source evidence':'Inspect the source';
  $('review-note').hidden=state.mode!=='review';
  if (!unit) {
    $('evidence-detail').innerHTML=`<div class="detail-section"><h3>${state.data?.document?'Select a detection':'Source PDF only'}</h3><p class="muted small">${state.data?.document?'Use the evidence picker or click a region on the PDF.':'This parser reference has not been converted. No indexed regions or result annotations exist yet.'}</p></div>`;
    return;
  }
  const check=record ? checkFor(record.result_id):null;
  const issues=[...new Set([...unit.issues,...(check?.warnings || []),...(check?.errors || [])])];
  let markup='';
  if (record) {
    markup=`<div class="value-block"><span class="field-label">Reported value</span><div class="reported-value">${escape(record.value.raw)}</div><span class="badge ${check?.outcome==='evidence_checks_passed'?'pass':'warning'}">Check: ${escape(readable(check?.outcome))}</span><span class="badge neutral">Review: ${escape(readable(record.review.status))}</span></div>${field('Method',record.method.normalized?`${record.method.reported} / ${record.method.normalized}`:record.method.reported)}${field('Dataset',record.benchmark.dataset.reported)}${field('Metric',`${record.metric.name.reported} · ${record.metric.direction==='unknown'?'direction unknown':record.metric.direction+' is better'}`)}${field('Source',pagesLabel(unit))}<div class="detail-section"><h3>Comparison conditions</h3>${field('Reported scale',record.metric.reported_scale)}${field('Split',record.benchmark.split)}${field('Task',record.benchmark.task)}${field('Subset',record.benchmark.subset)}${record.conditions.map(c=>field(readable(c.key),`${c.value} (${readable(c.basis)})`)).join('')}</div><div class="detail-section"><h3>Supporting evidence</h3>${sourceButton(record.value_evidence.evidence_id,`Value: ${record.value.raw}`)}${sourceButton(record.method_evidence.evidence_id,`Method: ${record.method.reported}`)}${record.metric_evidence.map(link=>sourceButton(link.evidence_id,'Metric: '+units()[link.evidence_id]?.text)).join('')}${record.benchmark.evidence.map(link=>sourceButton(link.evidence_id,link.quote?`Dataset / protocol: ${link.quote}`:null)).join('')}${record.metric.definition_evidence.map(link=>sourceButton(link.evidence_id,'Metric definition: '+units()[link.evidence_id]?.text.slice(0,120))).join('')}</div>`;
  } else {
    const label=unit.label==='formula'?'Formula region':unit.kind==='picture'?'Detected picture':unit.kind==='table'?'Detected table':unit.kind==='table_cell'?'Extracted table cell':readable(unit.label);
    markup=`<div class="detail-section"><span class="badge pass">${escape(label)}</span>${field('Source',pagesLabel(unit))}${unit.kind==='picture'||unit.label==='formula'?'<div class="detail-section"><h3>Source crop</h3><img id="source-crop" alt="Selected region cropped from the original PDF" hidden style="width:100%;height:auto;border:1px solid var(--line);border-radius:5px"></div>':''}${unit.label==='formula'&&!unit.text.trim()?'<div class="notice">Formula region detected; transcription unavailable.</div>':unit.kind==='picture'?'<p class="muted small detail-section">Picture detection does not establish diagram meaning.</p>':unit.text?`<h3 class="detail-section">Extracted text</h3><div class="extracted-text">${escape(unit.text)}</div>`:''}</div>`;
    const context=Object.entries(unit.context).filter(([key,refs])=>key!=='cells'&&refs.length);
    if (context.length) markup+=`<div class="detail-section"><h3>Structural context</h3>${context.map(([key,refs])=>`<span class="field-label detail-section">${escape(readable(key))}</span>${refs.map(id=>sourceButton(id)).join('')}`).join('')}</div>`;
    if (unit.kind==='table') {
      const cells=(unit.context.cells || []).map(id=>units()[id]).filter(Boolean);
      markup+=`<div class="detail-section"><h3>Extracted cells (${cells.length})</h3>${cells.slice(0,80).map(cell=>sourceButton(cell.evidence_id,`Row ${cell.cell.row_start+1}, column ${cell.cell.col_start+1}: ${cell.text || '(empty)'}`)).join('')}${cells.length>80?'<p class="muted small">First 80 cells shown. Select other cells directly on the PDF or export the complete index.</p>':''}</div>`;
    }
  }
  if (issues.length) markup+=`<div class="detail-section"><h3>Review issues</h3><ul class="issue-list">${issues.map(issue=>`<li>${escape(issueNames[issue] || readable(issue))}</li>`).join('')}</ul></div>`;
  const coarse=unit.kind==='table_cell'&&unit.locations.some(l=>l.granularity!=='cell');
  if (coarse) markup+='<div class="notice">Only a table-level location is available. The highlight does not identify a precise cell.</div>';
  markup+=`<details><summary>Technical details</summary><pre>${escape(JSON.stringify({evidence_id:unit.evidence_id,item_ref:unit.item_ref,locations:unit.locations,issues:unit.issues,document_id:state.data.document?.document_id,source_sha256:state.data.source_sha256},null,2))}</pre></details><p class="muted small detail-section">${record?'Provisional curated annotation. Automated checks establish limited attribution; independent human review is pending.':'Source locations come from the saved conversion. Structural context is not a verified semantic relationship.'}</p>`;
  $('evidence-detail').innerHTML=markup;
  updateCrop();
}
function renderComparison() {
  $('comparison').innerHTML=`<h2>Reported experiments</h2><div class="notice">Comparison pending · compatibility rules and independent review are not implemented.</div><p class="comparison-intro">Browse provisional annotations by dataset and metric. These rows are not a ranked leaderboard. Select a value to inspect its original evidence.</p>${records().length?`<div class="table-scroll"><table class="comparison-table"><thead><tr><th>Method</th><th>Dataset</th><th>Metric</th><th>Raw value</th><th>Check / review</th></tr></thead><tbody>${records().map(r=>`<tr><td>${escape(r.method.normalized || r.method.reported)}</td><td>${escape(r.benchmark.dataset.reported)}</td><td>${escape(r.metric.name.reported)}</td><td><button data-result="${escape(r.result_id)}">${escape(r.value.raw)} ↗</button></td><td>${escape(readable(checkFor(r.result_id)?.outcome))}<br><span class="muted">${escape(readable(r.review.status))}</span></td></tr>`).join('')}</tbody></table></div>`:'<p class="muted">This paper has no structured experiment annotations yet.</p>'}`;
}
function setMode(mode) {
  state.mode=mode;
  document.querySelectorAll('[data-mode]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.mode===mode)));
  $('comparison').hidden=mode!=='compare'; $('source').hidden=mode==='compare';
  if (mode==='review') {
    state.category='results';
    const record=records().filter(flagged)[0];
    if (record) {state.record=record.result_id; state.selection=record.value_evidence.evidence_id;}
  }
  renderPicker(); renderDetail(); renderComparison();
  if(mode!=='compare') navigateSelection();
}
function selectResult(id) {
  const record=records().find(r=>r.result_id===id);
  if (!record) return;
  state.record=id; state.selection=record.value_evidence.evidence_id; state.category='results';
  renderPicker(); renderDetail(); navigateSelection();
}
function selectEvidence(id) {
  if (!units()[id]) return;
  state.selection=id; state.record=null;
  const category=unitCategory(units()[id]);
  if (categories[category]) state.category=category;
  renderPicker(); renderDetail(); navigateSelection();
}
function navigateSelection() {
  const unit=units()[state.selection];
  if (!unit) return;
  const loc=unit.locations.find(l=>l.page_no===state.page)||unit.locations[0];
  if (!loc) { $('selection-location').textContent='Source location unavailable'; drawRegions(); return; }
  $('selection-location').textContent=`${pagesLabel(unit)} · ${loc.granularity==='table'&&unit.kind==='table_cell'?'Table-level location':readable(unit.label)}${loc.display_rect?'':' · No drawable bounding box'}`;
  if (!state.pdf) return;
  if (loc.page_no!==state.page) {state.page=loc.page_no; renderPage(true);}
  else {drawRegions(); updateCrop(); focusRegion(); remember();}
}
function supportIds() {
  const record=records().find(r=>r.result_id===state.record), unit=units()[state.selection];
  return new Set(record ? [record.method_evidence.evidence_id,...record.metric_evidence.map(l=>l.evidence_id)] : [...(unit?.context.row_headers || []),...(unit?.context.row_labels || []),...(unit?.context.column_headers || [])]);
}
function pixelRect(rect) {
  if (!rect || !state.pageProxy || !state.viewport) return null;
  const [x0,y0,x1,y1]=state.pageProxy.view, width=x1-x0,height=y1-y0;
  const first=state.viewport.convertToViewportPoint(x0+rect.left*width,y0+(1-rect.bottom)*height);
  const second=state.viewport.convertToViewportPoint(x0+rect.right*width,y0+(1-rect.top)*height);
  const projected=[...first,...second];
  return {left:Math.min(projected[0],projected[2]),top:Math.min(projected[1],projected[3]),width:Math.abs(projected[2]-projected[0]),height:Math.abs(projected[3]-projected[1])};
}
function drawRegions() {
  const container=$('region-layer'); container.replaceChildren(); container.hidden=!$('overlays').checked;
  if (!state.viewport || container.hidden) return;
  const active=new Set([...document.querySelectorAll('[data-layer]:checked')].map(c=>c.dataset.layer));
  const selected=units()[state.selection], support=supportIds();
  const order=Object.values(units()).sort((a,b)=>(a.kind==='table_cell')-(b.kind==='table_cell'));
  for (const unit of order) {
    const chosen=unit.evidence_id===state.selection, related=support.has(unit.evidence_id);
    const cat=unitCategory(unit);
    const cell=unit.kind==='table_cell' && unit.item_ref===selected?.item_ref && active.has('table');
    if (!chosen&&!related&&!active.has(cat)&&!cell) continue;
    if (unit.kind==='table_cell'&&!chosen&&!related&&!cell) continue;
    for (const location of unit.locations.filter(l=>l.page_no===state.page)) {
      const rect=pixelRect(location.display_rect); if(!rect) continue;
      const button=document.createElement('button'); button.type='button';
      button.className=`region ${unit.kind==='table_cell'?'table_cell':cat} ${chosen?'selected':related?'support':''}`;
      button.dataset.evidence=unit.evidence_id;
      const label=`${readable(unit.label)}: ${unitTitle(unit).slice(0,140)}${location.granularity==='table'&&unit.kind==='table_cell'?' (table-level location)':''}`;
      button.setAttribute('aria-label',label); button.title=label;
      Object.assign(button.style,{left:`${rect.left}px`,top:`${rect.top}px`,width:`${rect.width}px`,height:`${rect.height}px`});
      if (chosen) {const tag=document.createElement('span'); tag.className='region-label'; tag.textContent=location.granularity==='table'&&unit.kind==='table_cell'?'Table-level source':'Selected evidence'; button.append(tag);}
      container.append(button);
    }
  }
}
function focusRegion() {
  const selected=$('region-layer').querySelector('.selected');
  if (selected) selected.scrollIntoView({block:'center',inline:'nearest'});
}
function updateCrop() {
  const image=$('source-crop'); if(!image) return;
  const unit=units()[state.selection];
  const loc=unit?.locations.find(l=>l.page_no===state.page), rect=pixelRect(loc?.display_rect);
  const canvas=$('pdf-canvas');
  if (!rect||!canvas.width||!state.viewport||state.renderTask) {image.hidden=true; return;}
  const factor=canvas.width/state.viewport.width;
  const sx=Math.max(0,rect.left*factor),sy=Math.max(0,rect.top*factor),sw=Math.min(canvas.width-sx,rect.width*factor),sh=Math.min(canvas.height-sy,rect.height*factor);
  if(sw<=0||sh<=0) return;
  const output=document.createElement('canvas'), ratio=Math.min(1,1000/Math.max(sw,sh));
  output.width=Math.max(1,Math.round(sw*ratio)); output.height=Math.max(1,Math.round(sh*ratio));
  output.getContext('2d').drawImage(canvas,sx,sy,sw,sh,0,0,output.width,output.height);
  image.src=output.toDataURL('image/png'); image.hidden=false;
}
async function renderPage(focus=false) {
  if (!state.pdf) return;
  const serial=++state.renderSerial, epoch=state.epoch, pdf=state.pdf;
  state.renderTask?.cancel(); state.textTask?.cancel();
  $('region-layer').hidden=true;
  $('viewer-message').textContent=`Rendering page ${state.page}…`; controls(false);
  try {
    const page=await pdf.getPage(state.page);
    if(serial!==state.renderSerial||epoch!==state.epoch) return;
    const base=page.getViewport({scale:1});
    const padding=innerWidth<=620?24:44;
    const scale=$('zoom').value==='fit'?Math.max(.2,($('pdf-scroll').clientWidth-padding)/base.width):Number($('zoom').value);
    const viewport=page.getViewport({scale});
    state.pageProxy=page; state.viewport=viewport;
    const canvas=$('pdf-canvas'), dpr=Math.min(devicePixelRatio||1,2);
    canvas.width=Math.ceil(viewport.width*dpr); canvas.height=Math.ceil(viewport.height*dpr);
    canvas.style.width=`${viewport.width}px`; canvas.style.height=`${viewport.height}px`;
    $('pdf-page').style.width=`${viewport.width}px`; $('pdf-page').style.height=`${viewport.height}px`;
    $('pdf-page').style.setProperty('--scale-factor',String(scale));
    $('pdf-page').style.setProperty('--total-scale-factor',String(scale));
    $('pdf-page').style.setProperty('--user-unit',String(page.userUnit));
    $('pdf-page').hidden=false;
    const task=page.render({canvas,canvasContext:canvas.getContext('2d'),viewport,transform:dpr===1?null:[dpr,0,0,dpr,0,0]});
    state.renderTask=task;
    await task.promise;
    if(serial!==state.renderSerial||epoch!==state.epoch) return;
    state.renderTask=null;
    $('text-layer').replaceChildren();
    const textTask=new TextLayer({textContentSource:page.streamTextContent(),container:$('text-layer'),viewport});
    state.textTask=textTask;
    await textTask.render();
    if(serial!==state.renderSerial||epoch!==state.epoch) return;
    state.textTask=null;
    $('page-number').value=state.page; $('page-number').max=pdf.numPages; $('page-total').textContent=`/ ${pdf.numPages}`;
    $('viewer-message').textContent=''; controls(true); drawRegions(); updateCrop();
    if(focus) focusRegion(); else {$('pdf-scroll').scrollTop=0; $('pdf-scroll').scrollLeft=0;}
    status(`${pdf.numPages} pages · ${state.data.source_status}`); remember();
  } catch (cause) {
    if(serial!==state.renderSerial||epoch!==state.epoch||cause.name==='RenderingCancelledException'||cause.name==='AbortException') return;
    state.renderTask=null;
    $('viewer-message').textContent=`PDF rendering failed: ${cause.message}`;
    error('The original PDF could not be rendered. You can still inspect indexed evidence or open the original PDF.');
    controls(true);
  }
}
async function loadPaper(id) {
  const epoch=++state.epoch;
  state.controller?.abort(); state.renderTask?.cancel(); state.textTask?.cancel();
  if (state.loadTask) state.loadTask.destroy().catch(()=>{});
  state.controller=new AbortController();
  state.paper=id; state.data=null; state.pdf=null; state.viewport=null; state.pageProxy=null; state.selection=null; state.record=null; state.renderTask=null; state.textTask=null; state.renderSerial++;
  error(''); controls(false); $('export-open').disabled=true; $('pdf-page').hidden=true;
  $('evidence-picker').disabled=true; $('evidence-category').disabled=true; $('evidence-detail').textContent='Loading source evidence…';
  $('viewer-message').textContent='Checking saved evidence and source fingerprints…'; status('Loading source evidence…'); renderLibrary();
  $('paper-title').textContent=state.papers.find(p=>p.paper_id===id)?.title || 'Loading paper';
  $('document-summary').textContent=''; $('original-link').hidden=true;
  try {
    const response=await fetch(endpoint(''),{signal:state.controller.signal});
    const data=await response.json(); if(!response.ok) throw new Error(data.detail || 'Document request failed');
    if(epoch!==state.epoch) return;
    state.data=data; state.page=1; state.category=data.records.length?'results':'table';
    $('paper-role').textContent=roles[data.paper.role] || readable(data.paper.role);
    $('paper-title').textContent=data.paper.title;
    const pageCount=Object.keys(data.document?.pages || {}).length;
    $('document-summary').textContent=data.document?`${pageCount} pages · ${data.counts.table||0} tables · ${data.counts.picture||0} pictures · ${data.records.length} provisional annotations`:'Source PDF available · not converted or indexed';
    $('review-count').textContent=records().filter(flagged).length;
    $('original-link').href=endpoint('/pdf'); $('original-link').hidden=false;
    $('export-open').disabled=!data.exports.length;
    const defaultRecord=data.records[0];
    if(defaultRecord) {state.record=defaultRecord.result_id; state.selection=defaultRecord.value_evidence.evidence_id;}
    else state.selection=Object.values(data.units).find(u=>u.kind==='table')?.evidence_id || Object.keys(data.units)[0] || null;
    if(restoring?.paper===id&&restoring.document===data.document?.document_id) {
      if(units()[restoring.selection]) state.selection=restoring.selection;
      if(records().some(r=>r.result_id===restoring.record)) state.record=restoring.record;
      if(categories[restoring.category]) state.category=restoring.category;
      state.page=restoring.page||1;
    }
    const requested=records().find(r=>r.result_id===params.get('result'));
    if(requested&&params.get('paper')===id) {state.record=requested.result_id; state.selection=requested.value_evidence.evidence_id; state.category='results';}
    const loc=units()[state.selection]?.locations[0];
    if (!restoring || restoring.paper!==id) state.page=loc?.page_no||1;
    const requestedPage=Number(params.get('page'));
    if(params.get('paper')===id && Number.isInteger(requestedPage)&&requestedPage>0) state.page=requestedPage;
    renderPicker(); renderDetail(); renderComparison();
    $('viewer-message').textContent='Opening the original PDF…';
    const task=getDocument({url:endpoint('/pdf'),cMapUrl:'/static/vendor/cmaps/',cMapPacked:true,standardFontDataUrl:'/static/vendor/standard_fonts/',wasmUrl:'/static/vendor/wasm/',isEvalSupported:false});
    state.loadTask=task;
    const pdf=await task.promise; if(epoch!==state.epoch) {await pdf.destroy();return;}
    state.pdf=pdf; state.page=Math.max(1,Math.min(state.page,pdf.numPages));
    if(data.document && Object.keys(data.document.pages).length!==pdf.numPages) throw new Error('PDF page count differs from the saved evidence index');
    setMode('inspect');
    await renderPage(true);
  } catch(cause) {
    if(epoch!==state.epoch||cause.name==='AbortError') return;
    error(cause.message); $('viewer-message').textContent='Source could not be opened. Check the corpus paths and source identity.';
    if(!state.data) $('evidence-detail').textContent='Evidence unavailable for this document.';
    status('Document loading failed');
  }
}
function changePage(value) {
  if(!state.pdf) return;
  const page=Number(value);
  if(!Number.isInteger(page)||page<1||page>state.pdf.numPages) {$('page-number').value=state.page;return;}
  state.page=page; renderPage();
}
$('papers').addEventListener('click',event=>{const button=event.target.closest('[data-paper]'); if(button) loadPaper(button.dataset.paper);});
$('paper-picker').addEventListener('change',event=>loadPaper(event.target.value));
$('workspace-nav').addEventListener('click',event=>{const button=event.target.closest('[data-mode]');if(button&&state.data) setMode(button.dataset.mode);});
$('evidence-category').addEventListener('change',event=>{
  state.category=event.target.value;
  if(state.category==='results') {const first=(state.mode==='review'?records().filter(flagged):records())[0];if(first) selectResult(first.result_id);else {state.selection=null;state.record=null;renderPicker();renderDetail();drawRegions();}}
  else {const first=Object.values(units()).find(u=>unitCategory(u)===state.category);if(first) selectEvidence(first.evidence_id);else {state.selection=null;state.record=null;renderPicker();renderDetail();drawRegions();}}
});
$('evidence-picker').addEventListener('change',event=>{if(state.category==='results') selectResult(event.target.value);else selectEvidence(event.target.value);});
$('evidence-detail').addEventListener('click',event=>{const button=event.target.closest('[data-evidence]');if(button) selectEvidence(button.dataset.evidence);});
$('region-layer').addEventListener('click',event=>{const button=event.target.closest('[data-evidence]');if(button) selectEvidence(button.dataset.evidence);});
$('comparison').addEventListener('click',event=>{const button=event.target.closest('[data-result]');if(button){setMode('inspect');selectResult(button.dataset.result);}});
$('page-prev').addEventListener('click',()=>changePage(state.page-1)); $('page-next').addEventListener('click',()=>changePage(state.page+1));
$('page-number').addEventListener('change',event=>changePage(event.target.value)); $('zoom').addEventListener('change',()=>renderPage(true));
$('overlays').addEventListener('change',()=>drawRegions()); document.querySelectorAll('[data-layer]').forEach(input=>input.addEventListener('change',()=>drawRegions()));
$('export-open').addEventListener('click',()=>{
  $('export-description').textContent=`${state.data.paper.title}. ${records().length?'These annotations are provisional; their evidence checks and review statuses travel with the exports.':'No structured result annotations exist for this paper.'}`;
  $('export-options').innerHTML=state.data.exports.map(kind=>`<a class="export-link" href="${endpoint(`/exports/${kind}`)}" download>${escape(exportTypes[kind][0])}<span>${escape(exportTypes[kind][1])}</span></a>`).join('');
  $('export-dialog').showModal();
});
$('export-close').addEventListener('click',()=>$('export-dialog').close());
let resizeTimer, previousWidth=0;
new ResizeObserver(entries=>{const width=Math.round(entries[0].contentRect.width);if(width===previousWidth)return;previousWidth=width;clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(state.pdf&&state.mode!=='compare'&&$('zoom').value==='fit')renderPage();},160);}).observe($('pdf-scroll'));
async function start() {
  try {
    const response=await fetch('/api/papers'); if(!response.ok) throw new Error('The document library could not be loaded');
    state.papers=await response.json();
    const candidate=state.paper||restoring?.paper;
    const paper=state.papers.find(p=>p.paper_id===candidate)||state.papers.find(p=>p.processed)||state.papers[0];
    renderLibrary(); if(paper) await loadPaper(paper.paper_id);else {status('No documents in corpus manifest');$('viewer-message').textContent='Add papers to data/corpus.json to begin.';}
  } catch(cause) {error(cause.message);status('Library loading failed');}
}
start();
