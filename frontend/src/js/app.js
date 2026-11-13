import {createPhasePlot} from './phase-plot.js?v=3';
const $ = id => document.getElementById(id);
const phasePlot = createPhasePlot();
let previewRevision = 0, startedAt = 0;
let cancelRequested = false;
let diagram = null, job = null;
const symbol = value => value[0] + value.slice(1).toLowerCase();
const format = (v,d=1) => Number.isFinite(v) ? v.toLocaleString(undefined,{maximumFractionDigits:d}) : 'Not available';
function html(tag,cls,text=''){const n=document.createElement(tag);if(cls)n.className=cls;n.textContent=text;return n;}
async function api(path,options={}){const response=await fetch(path,{...options,headers:{'Content-Type':'application/json',...options.headers}});const data=await response.json();if(!response.ok){const detail=typeof data.detail==='string'?data.detail:JSON.stringify(data.detail);throw new Error(detail||'The request failed.');}return data;}
function status(message, error = false, target = $('status')) {
  target.textContent = message;
  target.classList.toggle('error', error);
}
const uploadInput = $('upload');
const uploadStatus = (message, error = false) => status(message, error, $('upload-status'));
const elementSelects = [$('component-a'), $('component-b')];
let uploadedDatabase = null;
let pendingUpload = null;
let busy = false;

function showStageProgress(state = {}) {
  const order = ['temperature', 'seeding', 'mapping', 'validation'];
  const current = order.indexOf(state.stage);
  for (const step of document.querySelectorAll('[data-calc-step]')) {
    const name = step.dataset.calcStep, index = order.indexOf(name);
    const active = index === current, done = current >= 0 && index < current;
    const work = state.stage_progress?.[name] || (active ? state : {});
    const total = work.total_steps, completed = work.completed_steps || 0;
    const known = Number.isFinite(total) && total > 0;
    step.classList.toggle('active', active);
    step.classList.toggle('done', done);
    step.classList.toggle('indeterminate', active && !known);
    step.style.setProperty('--step-fill', `${done ? 100 : known ? Math.min(100, 100*completed/total) : 0}%`);
    step.querySelector('.step-count').textContent = done ? 'Done' : known
      ? `${work.progress_label ? work.progress_label+' · ' : ''}${completed.toLocaleString()} / ${total.toLocaleString()}`
      : active ? 'In progress' : '';
    if(active)step.setAttribute('aria-current', 'step');else step.removeAttribute('aria-current');
    step.setAttribute('aria-label', `${step.querySelector('.step-name').textContent}: ${done ? 'done' : known ? `${completed} of ${total} ${work.step_unit || 'steps'}` : active ? 'in progress' : 'waiting'}`);
  }
}

function calculationSettings() {
  const [nx, nt] = $('resolution').value.split(',').map(Number);
  const auto = $('temperature-mode').value === 'auto';
  $('temperature-help').hidden = !auto;
  return {
    components: elementSelects.map(select => select.value),
    database_id: uploadedDatabase.id,
    uncertainty_note: 'Exploratory calculation using the uploaded file. Assessment coverage may be unverified.',
    temperature_mode: auto ? 'auto' : 'manual',
    temperature_min: auto ? 300 : Number($('tmin').value), temperature_max: auto ? 1200 : Number($('tmax').value),
    pressure: Number($('pressure').value), composition_points: nx, temperature_points: nt,
    boundary_steps: Number($('resolution').selectedOptions[0].dataset.steps),
    boundary_tolerance: Number($('boundary-tolerance').value)/100,
    cpu_workers: Number($('cpu-workers').value)
  };
}

function updateControls() {
  const [a, b] = elementSelects.map(select => select.value);
  for (const select of elementSelects) select.disabled = busy || !uploadedDatabase;
  $('calculate').disabled = busy || !uploadedDatabase || !a || !b || a === b;
  const auto = $('temperature-mode').value === 'auto';
  $('manual-temperatures').hidden = auto;
  $('tmin').disabled = busy || auto;
  $('tmax').disabled = busy || auto;
}
$('temperature-mode').addEventListener('change', updateControls);

for (const select of elementSelects) {
  select.addEventListener('change', () => {
    updateControls();
    const [a, b] = elementSelects.map(control => control.value);
    if (a && a === b) status('Choose two different elements.', true);
    else if (a && b) status('');
    else status('Choose two elements from the uploaded file.');
  });
}

$('diagram-form').addEventListener('invalid', event => {
  const settings = event.target.closest('details');
  if (settings) settings.open = true;
}, true);

uploadInput.addEventListener('change', async () => {
  pendingUpload?.abort();
  pendingUpload = null;
  const file = uploadInput.files[0];
  uploadedDatabase = null;
  diagram = null; phasePlot.reset();
  $('workspace').dataset.stage = 'setup';
  $('diagram-panel').hidden = true; $('inspector').hidden = true;
  $('export').disabled = true;
  for (const select of elementSelects) select.replaceChildren(new Option('Upload a file first', ''));
  status('');
  updateControls();
  if (!file) {
    uploadStatus('Upload a .tdb or .tbd file to begin.');
    return;
  }
  const controller = new AbortController();
  const {signal} = controller;
  pendingUpload = controller;
  const timeout = setTimeout(() => {
    controller.abort(new Error('Loading timed out. Choose the file again to retry.'));
  }, 60_000);
  uploadStatus(`Reading ${file.name}…`);
  try {
    if (!/\.(tdb|tbd)$/i.test(file.name)) throw new Error('Choose a .tdb or .tbd file.');
    if (file.size > 10 * 1024 * 1024) throw new Error('Choose a file no larger than 10 MB.');
    const content = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error('The file could not be read.'));
      reader.onload = () => resolve(reader.result.split(',')[1]);
      reader.onabort = () => reject(signal.reason);
      signal.addEventListener('abort', () => reader.abort(), {once: true});
      reader.readAsDataURL(file);
    });
    const database = await api('/api/databases', {
      method: 'POST', body: JSON.stringify({filename: file.name, content, encoding: 'base64'}), signal
    });
    if (pendingUpload !== controller) return;
    if (database.parse_error) throw new Error('Could not read this thermodynamic file: ' + database.parse_error);
    if (!database.capabilities.includes('thermodynamic')) throw new Error('This file has no Gibbs-energy data.');
    const elements = database.elements.filter(element => /^[A-Z]{1,2}$/.test(element));
    if (elements.length < 2) throw new Error('This file must contain at least two elements.');
    uploadedDatabase = database;
    for (const [index, select] of elementSelects.entries()) {
      select.replaceChildren(new Option('Select an element', ''),
        ...elements.map(element => new Option(symbol(element), element)));
      if (elements.length === 2) select.value = elements[index];
    }
    uploadStatus(elements.length === 2 ? '' : `Choose two of its ${elements.length} elements.`);
  } catch (error) {
    if (pendingUpload !== controller) return;
    uploadInput.value = '';
    uploadStatus(error.message, true);
  } finally {
    clearTimeout(timeout);
    if (pendingUpload === controller) {
      pendingUpload = null;
      updateControls();
    }
  }
});

function setBusy(value) {
  busy = value;
  for (const control of $('diagram-form').elements) control.disabled = value;
  $('cancel').disabled = false;
  $('cancel').hidden = !value;
  updateControls();
}

$('diagram-form').addEventListener('submit', async event => {
  event.preventDefault();
  if ($('calculate').disabled) return;
  const settings = calculationSettings();
  if (settings.temperature_mode === 'manual' && settings.temperature_max <= settings.temperature_min) {
    $('calculation-settings').open = true;
    $('tmax').focus();
    status('Maximum temperature must exceed minimum temperature.', true);
    return;
  }
  setBusy(true);
  startedAt = performance.now();
  cancelRequested = false;
  previewRevision = 0;
  $('workspace').dataset.stage = 'running';
  phasePlot.reset();
  $('quality-summary').textContent = '';
  $('plot-note').textContent = '';
  $('temperature-summary').textContent = '';
  $('plot-conditions').hidden = true;
  $('temperature-step').hidden = settings.temperature_mode !== 'auto';
  showStageProgress();
  $('calculation-live').hidden = false;
  $('inspector').hidden = true;
  $('diagram-panel').hidden = false;
  $('diagram-panel').setAttribute('aria-busy', 'true');
  $('export').disabled = true;
  $('system-title').textContent = settings.components.map(symbol).join(' — ');
  $('live-stage').textContent = 'Preparing the thermodynamic models';
  $('live-detail').textContent = 'Preparing the worker…';
  $('live-counts').textContent = '';
  $('legend').replaceChildren();
  $('warnings').hidden = true;
  $('warnings').open = false;
  $('provenance').hidden = true;
  $('provenance').open = false;
  $('plot').replaceChildren();
  $('empty').hidden = false;
  $('empty').textContent = 'Waiting for the first boundary preview.';
  status('');
  try {
    job = (await api('/api/diagrams', {method: 'POST', body: JSON.stringify(settings)})).id;
    if (cancelRequested) await api(`/api/jobs/${job}`, {method:'DELETE'});
    poll();
  } catch (error) {
    job = null;
    setBusy(false);
    status(error.message, true);
    finishInterrupted('Could not start calculation');
  }
});

function finishInterrupted(message) {
  $('diagram-panel').setAttribute('aria-busy','false');
  $('calculation-live').hidden = false;
  $('live-stage').textContent = message;
  $('live-detail').textContent = 'Partial previews are incomplete. Adjust the settings or create a new diagram.';
  $('workspace').dataset.stage = 'interrupted';
}

async function poll() {
  if (!job) return;
  const current = job;
  try {
    const state = await api(`/api/jobs/${current}`);
    if (current !== job) return;
    if (state.state === 'running') {
      if (!cancelRequested) status('');
      $('live-stage').textContent = ({temperature:'Finding the melting range', seeding:'Finding starting equilibria', mapping:'Tracing phase boundaries', validation:'Checking the boundary map'})[state.stage] || 'Preparing calculation';
      $('live-detail').textContent = state.message || 'Loading the database and preparing thermodynamic models';
      const counts = state.checks || {};
      $('live-counts').textContent = [state.boundary_points ? `${state.boundary_points.toLocaleString()} boundary points` : '', counts.disagreement ? `${counts.disagreement} disagreements` : '', `${Math.round((performance.now()-startedAt)/1000)} s elapsed`].filter(Boolean).join(' · ');
      showStageProgress(state);
      if (state.preview_revision && state.preview_revision !== previewRevision) {
        const preview = await api(`/api/jobs/${current}/preview`);
        if (current !== job) return;
        // No axes until the auto range is resolved; placeholder request limits
        // must not be presented as a calculated temperature range.
        if (state.stage !== 'temperature') phasePlot.render(preview, false);
        if (state.stage !== 'temperature') showConditions(preview.settings);
        previewRevision = preview.revision;
      }
      setTimeout(poll, 1000);
      return;
    }
    if (state.state === 'completed') {
      const result = await api(`/api/jobs/${current}/result`);
      if (current !== job) return;
      diagram = result;
      phasePlot.render(diagram);
      $('calculation-live').hidden = true;
      $('inspector').hidden = false;
      $('workspace').dataset.stage = 'complete';
      $('diagram-panel').setAttribute('aria-busy','false');
      $('export').disabled = false;
      $('system-title').textContent = `${diagram.settings.components.map(symbol).join(' — ')} equilibrium`;
      showConditions(diagram.settings);
      $('warning-content').replaceChildren();
      for (const warning of diagram.warnings) $('warning-content').append(html('p','',warning));
      $('warning-count').textContent = diagram.warnings.length;
      $('warnings').hidden = !diagram.warnings.length;
      $('provenance').hidden = false;
      $('provenance-content').replaceChildren();
      for (const [name,value] of Object.entries({...diagram.provenance, boundary_mapping:diagram.boundaries.method, mapping_notes:diagram.boundaries.notes, fallback_reason:diagram.boundaries.fallback_reason, validation:diagram.validation})) {
        if (value !== undefined) $('provenance-content').append(html('p','',`${name.replaceAll('_',' ')}: ${typeof value==='object'?JSON.stringify(value):value}`));
      }
      status('');
    } else {
      const message=state.state === 'failed' ? state.error : 'Calculation cancelled.';
      status(message,state.state === 'failed');
      finishInterrupted(message);
    }
    job = null;
    setBusy(false);
  } catch (error) {
    // Retain the job ID and cancellation control after a transient poll failure.
    status(`Connection interrupted: ${error.message}. Retrying…`, true);
    setTimeout(poll, 2000);
  }
}
function showConditions(settings) {
  $('plot-note').textContent = `${format(settings.pressure/1000,3)} kPa`;
  $('temperature-summary').textContent = settings.temperature_mode === 'auto'
    ? `Auto range: ${format(settings.temperature_min,0)}–${format(settings.temperature_max,0)} K` : '';
  $('plot-conditions').hidden = false;
}
$('cancel').addEventListener('click', async()=> {
  if(!busy)return;
  cancelRequested = true;
  status('Requesting cancellation…');
  if(job)try {await api(`/api/jobs/${job}`,{method:'DELETE'});}catch(error){status(error.message,true);}
});
$('export').addEventListener('click',()=> {
  if(!diagram)return;
  const url=URL.createObjectURL(new Blob([JSON.stringify(diagram,null,2)],{type:'application/json'})),link=document.createElement('a');
  link.href=url;link.download=`rutile-${diagram.settings.components.join('-')}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
uploadInput.disabled = false;
uploadStatus('Upload a .tdb or .tbd file to begin.');
updateControls();
