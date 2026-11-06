const $ = id => document.getElementById(id);
const NS = 'http://www.w3.org/2000/svg';
const colors = ['#dce8d2','#e1ddf1','#f4d9c9','#d5e8ed','#f2e8bb','#efdce6','#d3e5dc','#e1e5f1','#eddccb','#dce9be','#e8d9ed','#cfe1e5'];
let library = [], diagram = null, job = null, pinned = false, selected = null, colorMap = new Map(), materialToken = 0;
const plot = {left:76,top:25,width:670,height:465};
const symbol = value => value[0] + value.slice(1).toLowerCase();
const phaseKey = cell => cell.valid ? cell.phases.map(p => p.label).join(' + ') : 'Unresolved';
const format = (v,d=1) => Number.isFinite(v) ? v.toLocaleString(undefined,{maximumFractionDigits:d}) : 'Not available';
function node(tag,attrs={},text=''){const n=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);if(text)n.textContent=text;return n;}
function html(tag,cls,text=''){const n=document.createElement(tag);if(cls)n.className=cls;n.textContent=text;return n;}
async function api(path,options={}){const response=await fetch(path,{...options,headers:{'Content-Type':'application/json',...options.headers}});const data=await response.json();if(!response.ok){const detail=typeof data.detail==='string'?data.detail:JSON.stringify(data.detail);throw new Error(detail||'The request failed.');}return data;}
function status(message,error=false){$('status').textContent=message;$('status').classList.toggle('error',error);}
let decision = null;
let scanTimer;
let reviewToken = 0;
let busy = false;

function calculationSettings() {
  const [nx, nt] = $('resolution').value.split(',').map(Number);
  return {
    components: ['component-a', 'component-b'].map(id => $(id).value.trim().toUpperCase()),
    database_id: $('database').value || null,
    project_id: $('project-id').value.trim() || null,
    uncertainty_note: $('uncertainty-note').value.trim(),
    temperature_min: Number($('tmin').value), temperature_max: Number($('tmax').value),
    pressure: Number($('pressure').value), composition_points: nx, temperature_points: nt
  };
}

function updateButton() {
  const selected = decision?.candidates.find(candidate => candidate.id === (decision.pinned_id || decision.selected_id));
  $('calculate').disabled = busy || !selected?.eligible ||
    (selected.warnings.length > 0 && !$('uncertainty-note').value.trim());
}

function invalidateReview() {
  reviewToken++;
  decision = null;
  $('database').replaceChildren(new Option('Automatic', ''));
  $('database-info').textContent = 'Review sources for the current system and conditions.';
  $('assumptions').hidden = true;
  $('uncertainty-note').value = '';
  $('candidates').replaceChildren();
  updateButton();
}

function fillLibrary(preferred = $('library-file').value) {
  const query = $('library-search').value.toLowerCase().trim();
  const matches = library.filter(record => [record.label, record.source, record.id, record.elements.join(' '),
    ...record.locations.map(location => location.path)].some(value => value.toLowerCase().includes(query)));
  $('library-file').replaceChildren(new Option('Inspect a catalog file', ''));
  for (const record of matches.slice(0, 200)) {
    const issue = record.parse_error ? ' (parse failed)' : record.locations.some(location => location.available) ? '' : ' (unavailable)';
    $('library-file').add(new Option(record.label + issue, record.id));
  }
  if (matches.length > 200) {
    const more = new Option('Refine the search to see more files', '');
    more.disabled = true;
    $('library-file').add(more);
  }
  if (matches.slice(0, 200).some(record => record.id === preferred)) $('library-file').value = preferred;
  showFile();
}

function showFile() {
  const record = library.find(entry => entry.id === $('library-file').value);
  $('file-info').textContent = record ? [
    record.name, 'SHA-256 ' + record.sha256, record.parser,
    'Elements: ' + (record.elements.join(', ') || 'Unknown'),
    'Phases: ' + (record.phases.join(', ') || 'None detected'),
    'Capabilities detected: ' + (record.capabilities.join(', ') || 'None detected'),
    ...record.locations.map(location => (location.available ? '' : 'Unavailable: ') + location.path),
    record.parse_error, ...record.parser_warnings
  ].filter(Boolean).join('\n') : '';
}

async function refreshLibrary(preferred) {
  const result = await api('/api/databases');
  library = result.databases;
  $('source-roots').textContent = result.roots.join(' · ');
  $('scan-findings').replaceChildren(...result.findings.map(entry => html('li', '', entry.path + ' — ' + entry.message)));
  const elements = [...new Set(library.flatMap(record => record.elements))].sort();
  $('catalog-elements').replaceChildren(...elements.map(element => new Option(symbol(element))));
  fillLibrary(preferred);
}

async function monitorScan() {
  clearTimeout(scanTimer);
  try {
    const state = await api('/api/databases/scan');
    const running = state.state === 'running';
    $('scan').disabled = running;
    $('cancel-scan').hidden = !running;
    $('scan-status').textContent = state.state === 'idle' ? '' :
      `Scan ${state.state} · ${state.processed} files checked.${state.error ? ' ' + state.error : ''}`;
    if (running) scanTimer = setTimeout(monitorScan, 750);
    else if (state.state !== 'idle') {
      await refreshLibrary();
      invalidateReview();
    }
  } catch (error) {
    $('scan-status').textContent = error.message;
    $('scan').disabled = false;
  }
}

async function initialize() {
  drawAxes();
  invalidateReview();
  try {
    await refreshLibrary();
    $('library').open = !library.length;
    await monitorScan();
    const key = await api('/api/materials/status');
    $('key-settings').open = !key.configured;
  } catch (error) { status(error.message, true); }
}

function renderDecision(preferred) {
  $('database').replaceChildren(new Option('Automatic / saved preference', ''));
  for (const candidate of decision.candidates.filter(candidate => candidate.eligible)) {
    $('database').add(new Option(candidate.name + ' · ' + candidate.id.slice(0, 10), candidate.id));
  }
  if (preferred && Array.from($('database').options).some(option => option.value === preferred)) {
    $('database').value = preferred;
  }
  $('database-info').textContent = decision.message;
  $('candidates').replaceChildren(...decision.candidates.map(candidate => {
    const evidence = candidate.evidence;
    const details = [
      ...candidate.reasons, ...candidate.warnings,
      evidence.assessment ? 'Coverage evidence: ' + evidence.assessment : 'Coverage evidence: unknown',
      candidate.phases.length ? 'Compatible phases: ' + candidate.phases.join(', ') : '',
      ...Object.entries(candidate.detected_parameters).map(([family, phases]) =>
        'Detected ' + family + ' parameters: ' + phases.join(', ')),
      evidence.reference, evidence.citation, evidence.assessment_year, evidence.terms,
      evidence.temperature_k ? 'Documented K: ' + evidence.temperature_k.join('–') : '',
      evidence.pressure_pa ? 'Documented Pa: ' + evidence.pressure_pa.join('–') : '',
      ...Object.entries(evidence.composition_mole_fraction || {}).map(([element, bounds]) =>
        element + ' mole fraction: ' + bounds.join('–'))
    ].filter(Boolean);
    return html('li', '', [candidate.name + ' · ' + candidate.id.slice(0, 10), ...details].join(' · '));
  }));
  const pinned = decision.candidates.find(candidate => candidate.id === decision.pinned_id);
  $('assumptions').hidden = !(pinned?.eligible && pinned.warnings.length);
  updateButton();
}

async function reviewSources() {
  if (!$('diagram-form').reportValidity()) return;
  const settings = calculationSettings();
  const token = ++reviewToken;
  decision = null;
  updateButton();
  $('database-info').textContent = 'Reviewing candidate sources…';
  try {
    const composition = Object.fromEntries(settings.components.map(element => [element, [0, 1]]));
    const result = await api('/api/databases/selection', {
      method: 'POST', body: JSON.stringify({...settings, composition_mole_fraction: composition})
    });
    if (token !== reviewToken) return;
    decision = result;
    renderDecision(settings.database_id);
  } catch (error) {
    if (token === reviewToken) $('database-info').textContent = error.message;
  }
}

$('library-search').addEventListener('input', () => fillLibrary());
$('library-file').addEventListener('change', showFile);
$('add-root').addEventListener('click', async () => {
  try {
    await api('/api/databases/roots', {method: 'POST', body: JSON.stringify({path: $('source-root').value.trim()})});
    await refreshLibrary();
    $('source-root').value = '';
    $('scan-status').textContent = 'Folder registered. Scan source folders to add its files.';
  } catch (error) { $('scan-status').textContent = error.message; }
});
$('scan').addEventListener('click', async () => {
  $('scan').disabled = true;
  try {
    await api('/api/databases/scan', {method: 'POST'});
    await monitorScan();
  } catch (error) {
    $('scan-status').textContent = error.message;
    $('scan').disabled = false;
  }
});
$('cancel-scan').addEventListener('click', async () => {
  try { await api('/api/databases/scan', {method: 'DELETE'}); }
  catch (error) { $('scan-status').textContent = error.message; }
});
$('upload').addEventListener('change', async event => {
  const file = event.target.files[0];
  if (!file) return;
  try {
    if (file.size > 10 * 1024 * 1024) throw new Error('Choose a database no larger than 10 MB.');
    const content = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error('The file could not be read.'));
      reader.onload = () => resolve(reader.result.split(',')[1]);
      reader.readAsDataURL(file);
    });
    const imported = await api('/api/databases', {
      method: 'POST', body: JSON.stringify({filename: file.name, content, encoding: 'base64'})
    });
    $('library-search').value = '';
    await refreshLibrary(imported.id);
    invalidateReview();
    $('scan-status').textContent = `Imported ${imported.name}.`;
  } catch (error) { $('scan-status').textContent = error.message; }
  finally { event.target.value = ''; }
});

for (const id of ['component-a', 'component-b', 'tmin', 'tmax', 'pressure', 'project-id']) {
  $(id).addEventListener('input', invalidateReview);
}
for (const id of ['component-a', 'component-b']) $(id).addEventListener('change', resetMaterials);
$('new-project').addEventListener('click', () => {
  $('project-id').value = crypto.randomUUID();
  invalidateReview();
});
$('review-sources').addEventListener('click', reviewSources);
$('database').addEventListener('change', () => {
  $('uncertainty-note').value = '';
  reviewSources();
});
$('uncertainty-note').addEventListener('input', updateButton);
$('save-preference').addEventListener('click', async () => {
  if (!decision) return;
  const {components, database_id, project_id} = calculationSettings();
  const scope = $('preference-scope').value;
  if (scope !== 'library' && !project_id) {
    status('Enter or create a project ID before setting a project preference.', true);
    return;
  }
  try {
    await api('/api/databases/preference' + (scope === 'saved' ? '?saved=true' : ''), {
      method: 'PUT', body: JSON.stringify({components, database_id, project_id: scope === 'library' ? null : project_id})
    });
    $('database').value = '';
    await reviewSources();
    status(database_id ? 'Preference saved.' : 'Preference cleared.');
  } catch (error) { status(error.message, true); }
});

function setBusy(value) {
  busy = value;
  for (const control of $('diagram-form').elements) control.disabled = value;
  $('cancel').disabled = false;
  $('cancel').hidden = !value;
  $('progress').hidden = !value;
  updateButton();
}

$('diagram-form').addEventListener('submit', async event => {
  event.preventDefault();
  if ($('calculate').disabled) return;
  const settings = calculationSettings();
  setBusy(true);
  $('progress').value = 0;
  status('Starting equilibrium calculation…');
  try {
    job = (await api('/api/diagrams', {method: 'POST', body: JSON.stringify(settings)})).id;
    poll();
  } catch (error) {
    job = null;
    setBusy(false);
    status(error.message, true);
  }
});
async function poll(){if(!job)return;const current=job;try{const state=await api(`/api/jobs/${current}`);if(current!==job)return;if(state.state==='running'){$('progress').value=100*state.completed_rows/state.total_rows;status(`Calculating temperature row ${Math.min(state.completed_rows+1,state.total_rows)} of ${state.total_rows}…`);setTimeout(poll,900);return;}if(state.state==='completed'){diagram=await api(`/api/jobs/${current}/result`);if(current!==job)return;pinned=false;selected=null;renderDiagram();status(`Complete · ${diagram.cells.length.toLocaleString()} sampled equilibria.`);}else if(state.state==='failed')status(state.error,true);else status('Calculation cancelled.');job=null;setBusy(false);}catch(error){job=null;setBusy(false);status(error.message,true);}}
$('cancel').addEventListener('click',async()=>{if(!job)return;try{await api(`/api/jobs/${job}`,{method:'DELETE'});}catch(error){status(error.message,true);}});
function drawAxes(){const svg=$('plot');svg.replaceChildren();const defs=node('defs');const pattern=node('pattern',{id:'missing',width:8,height:8,patternUnits:'userSpaceOnUse'});pattern.append(node('rect',{width:8,height:8,fill:'#fafafa'}),node('path',{d:'M0 8L8 0',stroke:'#ddd', 'stroke-width':1}));defs.append(pattern);svg.append(defs);svg.append(node('rect',{x:plot.left,y:plot.top,width:plot.width,height:plot.height,fill:'#fcfcfa',stroke:'#e7e5df'}));const grid=node('g',{id:'cells'});svg.append(grid);for(let i=0;i<=5;i++){const x=plot.left+i/5*plot.width,y=plot.top+i/5*plot.height;svg.append(node('line',{x1:x,x2:x,y1:plot.top,y2:plot.top+plot.height,stroke:'#555',opacity:.07}));svg.append(node('line',{x1:plot.left,x2:plot.left+plot.width,y1:y,y2:y,stroke:'#555',opacity:.07}));svg.append(node('text',{x,y:plot.top+plot.height+25,'text-anchor':'middle',fill:'#706e66','font-size':13},String(i*20)));const low=diagram?.settings.temperature_min??300,high=diagram?.settings.temperature_max??1200;svg.append(node('text',{x:plot.left-13,y:y+4,'text-anchor':'end',fill:'#706e66','font-size':13},format(high-(high-low)*i/5,0)));}svg.append(node('text',{x:plot.left+plot.width/2,y:548,'text-anchor':'middle',fill:'#5c5c53','font-size':15},diagram?`${symbol(diagram.settings.components[1])} composition / atomic %`:'Composition / atomic %'));svg.append(node('text',{x:20,y:plot.top+plot.height/2,transform:`rotate(-90 20 ${plot.top+plot.height/2})`,'text-anchor':'middle',fill:'#5c5c53','font-size':15},'Temperature / K'));svg.append(node('g',{id:'region-labels','pointer-events':'none'}));svg.append(node('rect',{id:'selection',fill:'none',stroke:'#4c5545','stroke-width':2,visibility:'hidden','pointer-events':'none'}));}
function renderDiagram(){drawAxes();$('empty').hidden=true;$('export').disabled=false;const s=diagram.settings;$('system-title').textContent=s.components.map(symbol).join(' — ');$('plot-note').textContent=`${s.composition_points} × ${s.temperature_points} points · ${format(s.pressure/1000,3)} kPa`;$('plot').setAttribute('aria-label',`${s.components.map(symbol).join('-')} phase diagram. Arrow keys inspect cells, Enter pins, Escape unpins.`);const keys=[...new Set(diagram.cells.filter(c=>c.valid).map(phaseKey))].sort();colorMap=new Map(keys.map((key,i)=>[key,colors[i%colors.length]]));const group=$('cells');const w=plot.width/s.composition_points,h=plot.height/s.temperature_points;for(const cell of diagram.cells){group.append(node('rect',{x:plot.left+cell.xi*w,y:plot.top+plot.height-(cell.ti+1)*h,width:w+.15,height:h+.15,fill:cell.valid?colorMap.get(phaseKey(cell)):'url(#missing)'}));}regionLabels();$('legend').replaceChildren();for(const [key,color]of colorMap){const item=html('span','legend-item');const swatch=html('i','swatch');swatch.style.background=color;item.append(swatch,document.createTextNode(key));$('legend').append(item);}$('warnings').replaceChildren();for(const warning of diagram.warnings)$('warnings').append(html('p','',warning));$('warnings').hidden=!diagram.warnings.length;$('provenance').hidden=false;$('provenance-content').replaceChildren();for(const [key,value]of Object.entries(diagram.provenance))$('provenance-content').append(html('p','',`${key.replaceAll('_',' ')}: ${value}`));$('point-details').hidden=true;$('inspect-empty').hidden=false;resetMaterials();}
function regionLabels(){const s=diagram.settings,nx=s.composition_points,nt=s.temperature_points;const visited=new Set(),regions=[];for(let i=0;i<diagram.cells.length;i++){if(visited.has(i)||!diagram.cells[i].valid)continue;const key=phaseKey(diagram.cells[i]),indices=[],queue=[i];visited.add(i);for(let k=0;k<queue.length;k++){const index=queue[k];indices.push(index);const x=index%nx,y=Math.floor(index/nx);for(const [xx,yy]of [[x-1,y],[x+1,y],[x,y-1],[x,y+1]]){const j=yy*nx+xx;if(xx>=0&&xx<nx&&yy>=0&&yy<nt&&!visited.has(j)&&phaseKey(diagram.cells[j])===key){visited.add(j);queue.push(j);}}}if(indices.length>Math.max(8,nx*nt*.018)){const mx=indices.reduce((a,i)=>a+i%nx,0)/indices.length,my=indices.reduce((a,i)=>a+Math.floor(i/nx),0)/indices.length;const middle=indices.reduce((a,i)=>((i%nx-mx)**2+(Math.floor(i/nx)-my)**2)<((a%nx-mx)**2+(Math.floor(a/nx)-my)**2)?i:a);regions.push({key,index:middle,size:indices.length});}}const placed=[];for(const region of regions.sort((a,b)=>b.size-a.size)){const x=plot.left+(region.index%nx+.5)/nx*plot.width,y=plot.top+plot.height-(Math.floor(region.index/nx)+.5)/nt*plot.height;const lines=region.key.split(' + ');const width=Math.max(...lines.map(s=>s.length))*7+14,height=lines.length*17+8;if(placed.some(p=>Math.abs(p.x-x)<(p.width+width)/2&&Math.abs(p.y-y)<(p.height+height)/2+8))continue;if(x-width/2<plot.left||x+width/2>plot.left+plot.width)continue;placed.push({x,y,width,height});const label=node('g');label.append(node('rect',{x:x-width/2,y:y-height/2,width,height,rx:4,fill:'white',opacity:.72}));lines.forEach((line,i)=>label.append(node('text',{x,y:y-(lines.length-1)*8.5+i*17+4,'text-anchor':'middle','font-size':12,fill:'#45473e'},line)));$('region-labels').append(label);}}
function locate(event){if(!diagram)return null;const point=$('plot').createSVGPoint();point.x=event.clientX;point.y=event.clientY;const local=point.matrixTransform($('plot').getScreenCTM().inverse());const xi=Math.floor((local.x-plot.left)/plot.width*diagram.x.length),ti=Math.floor((plot.top+plot.height-local.y)/plot.height*diagram.temperatures.length);if(xi<0||xi>=diagram.x.length||ti<0||ti>=diagram.temperatures.length)return null;return diagram.cells[ti*diagram.x.length+xi];}
function inspect(cell){selected=cell;const nx=diagram.x.length,nt=diagram.temperatures.length;const selection=$('selection');for(const [k,v]of Object.entries({x:plot.left+cell.xi/nx*plot.width,y:plot.top+plot.height-(cell.ti+1)/nt*plot.height,width:plot.width/nx,height:plot.height/nt,visibility:'visible'}))selection.setAttribute(k,v);$('inspect-empty').hidden=true;$('point-details').hidden=false;$('point-temperature').textContent=`${format(diagram.temperatures[cell.ti],1)} K`;$('point-composition').textContent=`${format(diagram.x[cell.xi]*100,2)} at.% ${symbol(diagram.settings.components[1])} · sampled cell center`;$('gap-banner').hidden=!cell.miscibility_gap;$('unpin').hidden=!pinned;$('phase-cards').replaceChildren();if(!cell.valid)$('phase-cards').append(html('p','fine','No converged equilibrium at this point.'));for(const phase of cell.phases){const card=html('article','phase-card');const heading=html('h4','',phase.label);const swatch=html('span','swatch');swatch.style.background=colorMap.get(phaseKey(cell));heading.prepend(swatch);const amount=html('div','amount');amount.append(html('span','','Phase amount'),html('span','',`${format(phase.fraction*100,2)}%`));const bar=html('div','fraction-bar');const fill=html('span');fill.style.width=`${Math.min(100,phase.fraction*100)}%`;bar.append(fill);card.append(heading,amount,bar,html('p','composition-line',Object.entries(phase.composition).map(([c,x])=>`${symbol(c)} ${format(x*100,2)} at.%`).join(' · ')));$('phase-cards').append(card);}}
$('plot').addEventListener('pointermove',event=>{const cell=locate(event);if(!cell){$('tooltip').hidden=true;return;}if(!pinned)inspect(cell);const tooltip=$('tooltip');tooltip.textContent=`${format(diagram.temperatures[cell.ti])} K · ${format(diagram.x[cell.xi]*100)} at.% ${symbol(diagram.settings.components[1])}\n${phaseKey(cell)}${cell.miscibility_gap?'\nMiscibility gap — distinct compositions':''}`;tooltip.hidden=false;const box=$('plot-wrap').getBoundingClientRect();tooltip.style.left=`${Math.max(0,Math.min(event.clientX-box.left+15,box.width-tooltip.offsetWidth-5))}px`;tooltip.style.top=`${Math.max(0,event.clientY-box.top-tooltip.offsetHeight-15)}px`;});
$('plot').addEventListener('pointerleave',()=>{$('tooltip').hidden=true;});
$('plot').addEventListener('click',event=>{const cell=locate(event);if(cell){pinned=true;inspect(cell);showTab(false);}});
$('unpin').addEventListener('click',()=>{pinned=false;$('unpin').hidden=true;});
$('plot').addEventListener('keydown',event=>{if(!diagram)return;let x=selected?.xi??Math.floor(diagram.x.length/2),t=selected?.ti??Math.floor(diagram.temperatures.length/2);if(event.key==='Escape'){pinned=false;$('unpin').hidden=true;return;}if(event.key==='Enter'){event.preventDefault();pinned=!pinned;inspect(diagram.cells[t*diagram.x.length+x]);return;}if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;event.preventDefault();x+=event.key==='ArrowRight'?1:event.key==='ArrowLeft'?-1:0;t+=event.key==='ArrowUp'?1:event.key==='ArrowDown'?-1:0;x=Math.max(0,Math.min(diagram.x.length-1,x));t=Math.max(0,Math.min(diagram.temperatures.length-1,t));inspect(diagram.cells[t*diagram.x.length+x]);});
function showTab(materials){$('inspect-tab').setAttribute('aria-selected',String(!materials));$('materials-tab').setAttribute('aria-selected',String(materials));$('inspect-view').hidden=materials;$('materials-view').hidden=!materials;}
$('inspect-tab').addEventListener('click',()=>showTab(false));$('materials-tab').addEventListener('click',()=>showTab(true));$('find-materials').addEventListener('click',()=>{showTab(true);loadMaterials();});
function resetMaterials(){materialToken++;$('materials-list').replaceChildren();$('materials-status').textContent='Load crystal references when you are ready.';}
$('key-form').addEventListener('submit',async event=>{event.preventDefault();try{const data=await api('/api/materials/key',{method:'POST',body:JSON.stringify({key:$('api-key').value})});$('api-key').value='';$('key-settings').open=!data.configured;$('materials-status').textContent=data.configured?'Key set for this server session.':'Session key cleared.';}catch(error){$('materials-status').textContent=error.message;}});
async function loadMaterials(){const components=diagram?.settings.components??[$('component-a').value,$('component-b').value];if(components.some(c=>!c)){showTab(true);$('materials-status').textContent='Select two elements first.';return;}const token=++materialToken;$('load-materials').disabled=true;$('materials-status').textContent=`Loading ${components.map(symbol).join('–')} references…`;$('materials-list').replaceChildren();try{const payload=await api(`/api/materials?a=${encodeURIComponent(components[0])}&b=${encodeURIComponent(components[1])}`);if(token!==materialToken)return;const records=payload.data.sort((a,b)=>(a.energy_above_hull??Infinity)-(b.energy_above_hull??Infinity));for(const record of records){const card=html('article','material-card');const link=html('a','',record.formula_pretty+' ↗');link.href=`https://materialsproject.org/materials/${encodeURIComponent(record.material_id)}`;link.target='_blank';link.rel='noopener noreferrer';card.append(link,html('p','',`${record.symmetry?.symbol??'Unknown symmetry'} · ${record.symmetry?.crystal_system??'Unknown crystal system'}`),html('p','',`Density: ${format(record.density,3)}${Number.isFinite(record.density)?' g/cm³':''}`),html('p','',`Above hull: ${format(record.energy_above_hull,4)}${Number.isFinite(record.energy_above_hull)?' eV/atom':''}`),html('p','',`Elastic data: ${record.has_props?.elasticity?'available':'not available'}`),html('p','material-id',record.material_id));$('materials-list').append(card);}$('materials-status').textContent=`${records.length} references shown${payload.total?` of ${payload.total}`:''} · ${components.map(symbol).join('–')} and pure elements. ${records.length===payload.limit?'Results are limited to the first 60 records.':''}`;}catch(error){if(token===materialToken){$('materials-status').textContent=error.message;if(error.message.includes('key'))$('key-settings').open=true;}}finally{$('load-materials').disabled=false;}}
$('load-materials').addEventListener('click',loadMaterials);
$('export').addEventListener('click',()=>{if(!diagram)return;const blob=new Blob([JSON.stringify(diagram,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const link=html('a');link.href=url;link.download=`rutile-${diagram.settings.components.join('-')}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
initialize();
