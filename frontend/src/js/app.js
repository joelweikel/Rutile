const $ = id => document.getElementById(id);
const NS = 'http://www.w3.org/2000/svg';
const colors = ['#dce8d2','#e1ddf1','#f4d9c9','#d5e8ed','#f2e8bb','#efdce6','#d3e5dc','#e1e5f1','#eddccb','#dce9be','#e8d9ed','#cfe1e5'];
let diagram = null, job = null, pinned = false, selected = null, colorMap = new Map();
const plot = {left:76,top:25,width:670,height:465};
const symbol = value => value[0] + value.slice(1).toLowerCase();
const phaseKey = cell => cell.valid ? cell.phases.map(p => p.label).join(' + ') : 'Unresolved';
const format = (v,d=1) => Number.isFinite(v) ? v.toLocaleString(undefined,{maximumFractionDigits:d}) : 'Not available';
function node(tag,attrs={},text=''){const n=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);if(text)n.textContent=text;return n;}
function html(tag,cls,text=''){const n=document.createElement(tag);if(cls)n.className=cls;n.textContent=text;return n;}
async function api(path,options={}){const response=await fetch(path,{...options,headers:{'Content-Type':'application/json',...options.headers}});const data=await response.json();if(!response.ok){const detail=typeof data.detail==='string'?data.detail:JSON.stringify(data.detail);throw new Error(detail||'The request failed.');}return data;}
function status(message,error=false){$('status').textContent=message;$('status').classList.toggle('error',error);}
const elementSelects = [$('component-a'), $('component-b')];
let uploadedDatabase = null;
let busy = false;

function calculationSettings() {
  const [nx, nt] = $('resolution').value.split(',').map(Number);
  return {
    components: elementSelects.map(select => select.value),
    database_id: uploadedDatabase.id,
    uncertainty_note: 'Exploratory calculation using the uploaded file. Assessment coverage may be unverified.',
    temperature_min: Number($('tmin').value), temperature_max: Number($('tmax').value),
    pressure: Number($('pressure').value), composition_points: nx, temperature_points: nt
  };
}

function updateControls() {
  const [a, b] = elementSelects.map(select => select.value);
  for (const select of elementSelects) select.disabled = busy || !uploadedDatabase;
  $('calculate').disabled = busy || !uploadedDatabase || !a || !b || a === b;
}

for (const select of elementSelects) {
  select.addEventListener('change', () => {
    updateControls();
    const [a, b] = elementSelects.map(control => control.value);
    if (a && a === b) status('Choose two different elements.', true);
    else if (a && b) status('Ready to generate the diagram.');
    else status('Choose two elements from the uploaded file.');
  });
}

$('diagram-form').addEventListener('invalid', event => {
  const settings = event.target.closest('details');
  if (settings) settings.open = true;
}, true);

$('upload').addEventListener('change', async event => {
  const input = event.target;
  const file = input.files[0];
  uploadedDatabase = null;
  for (const select of elementSelects) select.replaceChildren(new Option('Select', ''));
  updateControls();
  if (!file) {
    status('Upload a .tdb or .tbd file to begin.');
    return;
  }
  input.disabled = true;
  status('Reading thermodynamic file…');
  try {
    if (!/\.(tdb|tbd)$/i.test(file.name)) throw new Error('Choose a .tdb or .tbd file.');
    if (file.size > 10 * 1024 * 1024) throw new Error('Choose a file no larger than 10 MB.');
    const content = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error('The file could not be read.'));
      reader.onload = () => resolve(reader.result.split(',')[1]);
      reader.readAsDataURL(file);
    });
    const database = await api('/api/databases', {
      method: 'POST', body: JSON.stringify({filename: file.name, content, encoding: 'base64'})
    });
    if (database.parse_error) throw new Error('Could not read this thermodynamic file: ' + database.parse_error);
    if (!database.capabilities.includes('thermodynamic')) throw new Error('This file has no Gibbs-energy data.');
    const elements = database.elements.filter(element => /^[A-Z]{1,2}$/.test(element));
    if (elements.length < 2) throw new Error('This file must contain at least two elements.');
    uploadedDatabase = database;
    for (const select of elementSelects) {
      select.append(...elements.map(element => new Option(symbol(element), element)));
    }
    status('Choose two elements from the uploaded file.');
  } catch (error) {
    input.value = '';
    status(error.message, true);
  } finally {
    input.disabled = false;
    updateControls();
  }
});

function setBusy(value) {
  busy = value;
  for (const control of $('diagram-form').elements) control.disabled = value;
  $('cancel').disabled = false;
  $('cancel').hidden = !value;
  $('progress').hidden = !value;
  updateControls();
}

$('diagram-form').addEventListener('submit', async event => {
  event.preventDefault();
  if ($('calculate').disabled) return;
  const settings = calculationSettings();
  if (settings.temperature_max <= settings.temperature_min) {
    $('calculation-settings').open = true;
    $('tmax').focus();
    status('Maximum temperature must exceed minimum temperature.', true);
    return;
  }
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
function renderDiagram(){drawAxes();$('empty').hidden=true;$('export').disabled=false;const s=diagram.settings;$('system-title').textContent=s.components.map(symbol).join(' — ');$('plot-note').textContent=`${s.composition_points} × ${s.temperature_points} points · ${format(s.pressure/1000,3)} kPa`;$('plot').setAttribute('aria-label',`${s.components.map(symbol).join('-')} phase diagram. Arrow keys inspect cells, Enter pins, Escape unpins.`);const keys=[...new Set(diagram.cells.filter(c=>c.valid).map(phaseKey))].sort();colorMap=new Map(keys.map((key,i)=>[key,colors[i%colors.length]]));const group=$('cells');const w=plot.width/s.composition_points,h=plot.height/s.temperature_points;for(const cell of diagram.cells){group.append(node('rect',{x:plot.left+cell.xi*w,y:plot.top+plot.height-(cell.ti+1)*h,width:w+.15,height:h+.15,fill:cell.valid?colorMap.get(phaseKey(cell)):'url(#missing)'}));}regionLabels();$('legend').replaceChildren();for(const [key,color]of colorMap){const item=html('span','legend-item');const swatch=html('i','swatch');swatch.style.background=color;item.append(swatch,document.createTextNode(key));$('legend').append(item);}$('warnings').replaceChildren();for(const warning of diagram.warnings)$('warnings').append(html('p','',warning));$('warnings').hidden=!diagram.warnings.length;$('provenance').hidden=false;$('provenance-content').replaceChildren();for(const [key,value]of Object.entries(diagram.provenance))$('provenance-content').append(html('p','',`${key.replaceAll('_',' ')}: ${value}`));$('point-details').hidden=true;$('inspect-empty').hidden=false;}
function regionLabels(){const s=diagram.settings,nx=s.composition_points,nt=s.temperature_points;const visited=new Set(),regions=[];for(let i=0;i<diagram.cells.length;i++){if(visited.has(i)||!diagram.cells[i].valid)continue;const key=phaseKey(diagram.cells[i]),indices=[],queue=[i];visited.add(i);for(let k=0;k<queue.length;k++){const index=queue[k];indices.push(index);const x=index%nx,y=Math.floor(index/nx);for(const [xx,yy]of [[x-1,y],[x+1,y],[x,y-1],[x,y+1]]){const j=yy*nx+xx;if(xx>=0&&xx<nx&&yy>=0&&yy<nt&&!visited.has(j)&&phaseKey(diagram.cells[j])===key){visited.add(j);queue.push(j);}}}if(indices.length>Math.max(8,nx*nt*.018)){const mx=indices.reduce((a,i)=>a+i%nx,0)/indices.length,my=indices.reduce((a,i)=>a+Math.floor(i/nx),0)/indices.length;const middle=indices.reduce((a,i)=>((i%nx-mx)**2+(Math.floor(i/nx)-my)**2)<((a%nx-mx)**2+(Math.floor(a/nx)-my)**2)?i:a);regions.push({key,index:middle,size:indices.length});}}const placed=[];for(const region of regions.sort((a,b)=>b.size-a.size)){const x=plot.left+(region.index%nx+.5)/nx*plot.width,y=plot.top+plot.height-(Math.floor(region.index/nx)+.5)/nt*plot.height;const lines=region.key.split(' + ');const width=Math.max(...lines.map(s=>s.length))*7+14,height=lines.length*17+8;if(placed.some(p=>Math.abs(p.x-x)<(p.width+width)/2&&Math.abs(p.y-y)<(p.height+height)/2+8))continue;if(x-width/2<plot.left||x+width/2>plot.left+plot.width)continue;placed.push({x,y,width,height});const label=node('g');label.append(node('rect',{x:x-width/2,y:y-height/2,width,height,rx:4,fill:'white',opacity:.72}));lines.forEach((line,i)=>label.append(node('text',{x,y:y-(lines.length-1)*8.5+i*17+4,'text-anchor':'middle','font-size':12,fill:'#45473e'},line)));$('region-labels').append(label);}}
function locate(event){if(!diagram)return null;const point=$('plot').createSVGPoint();point.x=event.clientX;point.y=event.clientY;const local=point.matrixTransform($('plot').getScreenCTM().inverse());const xi=Math.floor((local.x-plot.left)/plot.width*diagram.x.length),ti=Math.floor((plot.top+plot.height-local.y)/plot.height*diagram.temperatures.length);if(xi<0||xi>=diagram.x.length||ti<0||ti>=diagram.temperatures.length)return null;return diagram.cells[ti*diagram.x.length+xi];}
function inspect(cell){selected=cell;const nx=diagram.x.length,nt=diagram.temperatures.length;const selection=$('selection');for(const [k,v]of Object.entries({x:plot.left+cell.xi/nx*plot.width,y:plot.top+plot.height-(cell.ti+1)/nt*plot.height,width:plot.width/nx,height:plot.height/nt,visibility:'visible'}))selection.setAttribute(k,v);$('inspect-empty').hidden=true;$('point-details').hidden=false;$('point-temperature').textContent=`${format(diagram.temperatures[cell.ti],1)} K`;$('point-composition').textContent=`${format(diagram.x[cell.xi]*100,2)} at.% ${symbol(diagram.settings.components[1])} · sampled cell center`;$('gap-banner').hidden=!cell.miscibility_gap;$('unpin').hidden=!pinned;$('phase-cards').replaceChildren();if(!cell.valid)$('phase-cards').append(html('p','fine','No converged equilibrium at this point.'));for(const phase of cell.phases){const card=html('article','phase-card');const heading=html('h4','',phase.label);const swatch=html('span','swatch');swatch.style.background=colorMap.get(phaseKey(cell));heading.prepend(swatch);const amount=html('div','amount');amount.append(html('span','','Phase amount'),html('span','',`${format(phase.fraction*100,2)}%`));const bar=html('div','fraction-bar');const fill=html('span');fill.style.width=`${Math.min(100,phase.fraction*100)}%`;bar.append(fill);card.append(heading,amount,bar,html('p','composition-line',Object.entries(phase.composition).map(([c,x])=>`${symbol(c)} ${format(x*100,2)} at.%`).join(' · ')));$('phase-cards').append(card);}}
$('plot').addEventListener('pointermove',event=>{const cell=locate(event);if(!cell){$('tooltip').hidden=true;return;}if(!pinned)inspect(cell);const tooltip=$('tooltip');tooltip.textContent=`${format(diagram.temperatures[cell.ti])} K · ${format(diagram.x[cell.xi]*100)} at.% ${symbol(diagram.settings.components[1])}\n${phaseKey(cell)}${cell.miscibility_gap?'\nMiscibility gap — distinct compositions':''}`;tooltip.hidden=false;const box=$('plot-wrap').getBoundingClientRect();tooltip.style.left=`${Math.max(0,Math.min(event.clientX-box.left+15,box.width-tooltip.offsetWidth-5))}px`;tooltip.style.top=`${Math.max(0,event.clientY-box.top-tooltip.offsetHeight-15)}px`;});
$('plot').addEventListener('pointerleave',()=>{$('tooltip').hidden=true;});
$('plot').addEventListener('click',event=>{const cell=locate(event);if(cell){pinned=true;inspect(cell);}});
$('unpin').addEventListener('click',()=>{pinned=false;$('unpin').hidden=true;});
$('plot').addEventListener('keydown',event=>{if(!diagram)return;let x=selected?.xi??Math.floor(diagram.x.length/2),t=selected?.ti??Math.floor(diagram.temperatures.length/2);if(event.key==='Escape'){pinned=false;$('unpin').hidden=true;return;}if(event.key==='Enter'){event.preventDefault();pinned=!pinned;inspect(diagram.cells[t*diagram.x.length+x]);return;}if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;event.preventDefault();x+=event.key==='ArrowRight'?1:event.key==='ArrowLeft'?-1:0;t+=event.key==='ArrowUp'?1:event.key==='ArrowDown'?-1:0;x=Math.max(0,Math.min(diagram.x.length-1,x));t=Math.max(0,Math.min(diagram.temperatures.length-1,t));inspect(diagram.cells[t*diagram.x.length+x]);});
$('export').addEventListener('click',()=>{if(!diagram)return;const blob=new Blob([JSON.stringify(diagram,null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const link=html('a');link.href=url;link.download=`rutile-${diagram.settings.components.join('-')}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
drawAxes();
