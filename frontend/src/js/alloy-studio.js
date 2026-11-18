import {accepts, families, inputPort, materialId, nodeOf, operations, restoreGraph, starter} from './alloy-graph.js';
import {createStudioRuns, studioApi, studioPost} from './alloy-runs.js';
import {nearestPosition, wireSegment} from './alloy-layout.js';
import {mergeResearchPhaseData, phaseDataMarkup, removeEditedResearch} from './alloy-phase-data.js';
import {phaseAssignmentMarkup, phaseProperties} from './alloy-phase-inspector.js';
import {createReferenceResearch, researchTargets} from './alloy-reference-research.js';
import {initProcessingEvents, processingScheduleMarkup, renderSchedulePlot, restoreScheduleEvents, scheduleIssue, schedulePoints} from './processing-events.js';

const storageKey = 'rutile.alloy-studio.v1';
const esc = value => String(value ?? '').replace(/[&<>"']/g, character =>
  ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character]));
const format = value => Number(value).toLocaleString(undefined, {maximumSignificantDigits: 6});
const fileKinds = {
  assessmentFile: ['assessment', '.tdb,.tbd'], physicalFile: ['physical', '.pdb'], mobilityFile: ['mobility', '.ddb'],
};
const variableKinds = {assessmentFile: 'TDB', mobilityFile: 'DDB', physicalFile: 'PDB', phaseData: 'Phase'};

function savedWorkspace() {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey));
    return {graph: restoreGraph(saved.graph), runs: Array.isArray(saved.runs) ? saved.runs.slice(0, 100) : []};
  } catch {
    return {graph: {...starter(), researchProject: crypto.randomUUID()}, runs: []};
  }
}

function phaseTable(value) {
  const set = value.phase_set || value.final;
  return `<div class="studio-condition"><span>${format(set.temperature_k)} K</span>
    <span>${format(set.pressure_pa ?? value.settings.pressure_pa)} Pa</span></div>
    <table><thead><tr><th>Phase</th><th>mol%</th><th>Composition (at%)</th></tr></thead><tbody>
    ${set.phases.map(phase => `<tr><td>${esc(phase.label)}</td><td>${format(phase.fraction * 100)}</td>
      <td>${Object.entries(phase.composition).map(([element, amount]) => `${esc(element)} ${format(amount * 100)}`).join('<br>')}</td></tr>`).join('')}
    </tbody></table>${set.kind === 'final_phase_set' ? set.phases.map(phase =>
      `<details><summary>${esc(phase.label)} properties</summary>${phaseProperties(phase, esc, format)}</details>`).join('') : ''}
    <details><summary>Source and assumptions</summary><p>${esc(value.provenance.source_name)}</p>
    <code>${esc(value.provenance.source_sha256)}</code><ul>${value.assumptions.map(note => `<li>${esc(note)}</li>`).join('')}</ul></details>`;
}

function resultMarkup(node, saved) {
  if (!saved) return '';
  const result = saved.result;
  if (['viewer', 'equilibrium', 'phaseAssignment'].includes(node.type)) return phaseTable(result);
  if (node.type === 'density') {
    const properties = result.properties;
    const density = properties?.density;
    return densityMarkup(properties, density);
  }
  if (node.type === 'tracer') {
    const tracer = result.kawin;
    if (tracer.state !== 'completed') return `<p>Unavailable · ${esc(tracer.reason)}</p>`;
    return `<p>${esc(tracer.phase)} · ${format(tracer.temperature_k)} K · ${format(tracer.pressure_pa)} Pa</p>
      <ul>${Object.entries(tracer.tracer_diffusivity_m2_s).map(([element, value]) =>
        `<li>${esc(element)} · ${Number(value).toExponential(4)} m²/s</li>`).join('')}</ul><p class="fine">${esc(tracer.role)}</p>`;
  }
  return '';
}

function densityMarkup(properties, density) {
  const summary = density?.state === 'estimated'
    ? `<p class="studio-metric">${format(density.value_g_cm3)} <span>g/cm³</span></p><p>${esc(density.source)}</p>`
    : `<p class="studio-warning">Unavailable · ${esc(density?.reason || properties?.reason || 'Missing phase-volume data.')}</p>`;
  if (!properties?.phases) return summary;
  const coverage = 100 * properties.density_coverage_mole_fraction;
  return `${summary}<div class="studio-coverage"><span>Coverage</span><strong>${format(coverage)} mol%</strong>
    <meter min="0" max="100" value="${coverage}" aria-label="Density coverage in mol%"></meter></div>
    <ul class="studio-phase-coverage">${properties.phases.map(phase => {
      const model = phase.density_model;
      const detail = model?.state === 'estimated' ?
        `${format(model.value_g_cm3)} g/cm³ · ${model.source || `MatCalc DP · ${model.mapping?.mapping || 'local model'}`}` :
        phase.density_source || phase.phase_data?.reason || model?.reason || phase.reason || 'No applicable density reference';
      return `<li><strong>${esc(phase.label)}</strong><span>${esc(detail)}</span></li>`;
    }).join('')}</ul>`;
}

function selectField(settings, key, label, options) {
  return `<label><span>${label}</span><select data-field="${key}">${options.map(([value, title]) =>
    `<option value="${esc(value)}" ${value === settings[key] ? 'selected' : ''}>${esc(title)}</option>`).join('')}</select></label>`;
}

function balanceText(settings) {
  return `Balance · ${settings.base} ${format(100 - settings.amount)} ${settings.basis === 'mass' ? 'wt%' : 'at%'}`;
}

function inlineFields(node) {
  const settings = node.settings;
  const input = (key, label, type, attributes) => `<label><span>${label}</span>
    <input data-field="${key}" type="${type}" ${attributes} value="${esc(settings[key])}"></label>`;
  if (node.type === 'composition') return selectField(settings, 'base', 'Base element', families.map(key => [key, key])) +
    input('element', 'Addition element', 'text', 'maxlength="2" spellcheck="false"') +
    input('amount', 'Addition (%)', 'number', 'step="any" min="0" max="100"') +
    selectField(settings, 'basis', 'Composition basis', [['mass', 'wt%'], ['atomic', 'at%']]) +
    `<output class="studio-balance" data-balance>${esc(balanceText(settings))}</output>`;
  return '';
}

function settingsMarkup(node, catalog) {
  const s = node.settings;
  const fields = inlineFields(node);
  if (fields) return fields;
  if (node.type === 'schedule') return `<fieldset class="studio-schedule-editor">
      ${processingScheduleMarkup('studio-', s)}
      <p class="fine">Equilibrium at each thermal setpoint. Hold duration, quench medium, and cold work are recorded conditions.</p>
      <div class="studio-schedule-options">
        <label>Pressure (Pa)<input data-schedule-option="pressure" type="number" min="0" max="1000000000" step="any" value="${esc(s.pressure)}" required></label>
        <label data-cooling-controls ${s.route === 'arc_melting' ? '' : 'hidden'}>Cooling points<input data-schedule-option="points" type="number" min="3" max="61" value="${esc(s.points)}" required></label>
      </div>
    </fieldset>`;
  if (Object.hasOwn(fileKinds, node.type)) {
    const [role, accept] = fileKinds[node.type];
    const available = role === 'physical' ? [['configured', catalog?.physical?.name || 'Configured physical data']] :
      families.map(key => {
        const source = catalog?.sources.find(item => item.family === key);
        return [key, source?.[role === 'assessment' ? 'thermodynamic' : 'mobility'] || `MatCalc ${key}`];
      });
    return selectField(s, 'preset', 'File preset', [['', s.file ? 'Uploaded file' : 'Select a file preset'], ...available]) +
      `<label>Upload file<input type="file" data-source-file accept="${accept}"></label>
      ${s.file ? `<p>${esc(s.file.name)}</p><code>${esc(s.file.id)}</code>` : ''}`;
  }
  if (node.type === 'phaseData') return phaseDataMarkup(s, esc);
  if (node.type === 'phaseAssignment') return `<label><input type="checkbox" data-field="references"
    ${s.references ? 'checked' : ''}> Look up Materials Project references</label>`;
  if (node.type === 'density') return `<label><input type="checkbox" data-field="references" ${s.references ? 'checked' : ''}> Use compatible reference volumes</label>
    <label><input type="checkbox" data-field="parentDensity" ${s.parentDensity ? 'checked' : ''}> Allow disordered parent density</label>`;
  return '';
}

export function initAlloyStudio(root) {
  const saved = savedWorkspace();
  let graph = saved.graph, selected = graph.nodes.find(node => node.type === 'composition')?.id;
  let busy = false, opened = false, sourceCatalog, camera = {x: 24, y: 24, scale: 1};
  let gesture, armed, menuState, drawFrame, entryTimer, logEntries = [], suppressClick = false;
  let scheduleEditor, removedNode;
  const messages = new Map();
  const name = document.getElementById('studio-project-name');
  root.innerHTML = `<section class="studio-workspace" aria-label="Alloy workflow">
    <div class="studio-bar"><button class="glass-button" type="button" data-action="project" aria-expanded="false">Project</button>
      <button class="glass-button" type="button" data-action="add" aria-expanded="false">Add node</button>
      <button class="glass-button" type="button" data-action="fit">Fit graph</button>
      <button class="glass-button" type="button" data-action="zoom-out" aria-label="Zoom out">−</button>
      <button class="glass-button" type="button" data-action="zoom-in" aria-label="Zoom in">+</button>
      <button class="glass-button studio-right" type="button" data-action="inspector" aria-expanded="true">Inspector</button>
      <button class="primary" type="button" data-action="run">▶ Run graph</button></div>
    <div class="studio-body"><div class="studio-viewport" tabindex="0" aria-label="Workflow canvas">
      <div class="studio-world"><svg aria-hidden="true" class="studio-wires"></svg><div class="studio-nodes"></div><div class="studio-reroutes"></div></div>
      <div class="studio-library" hidden><input type="search" placeholder="Search nodes…" aria-label="Search nodes"><div class="studio-matches"></div></div>
    </div><aside class="studio-inspector" aria-label="Node inspector"></aside>
    <section class="studio-drawer studio-project" aria-label="Project" hidden><h2>Project</h2>
      <button type="button" class="glass-button" data-action="starter">Al–Cu starter</button>
      <button type="button" class="glass-button" data-action="blank">Blank workflow</button>
      <label>Open workflow<input type="file" data-open-graph accept=".rutile,.json"></label>
      <button type="button" class="glass-button" data-action="save">Export workflow</button>
      <details><summary>Guided setup</summary>
        <button type="button" class="glass-button" data-open="optimize" data-alloy-mode="create">Create alloy</button>
        <button type="button" class="glass-button" data-open="optimize" data-alloy-mode="optimize">Optimize alloy</button>
      </details>
    </section></div>
    <div class="studio-status"><output aria-live="polite">Ready</output><progress max="100" hidden aria-label="Calculation progress"></progress>
      <button type="button" class="glass-button" data-action="undo-remove" hidden>Undo removal</button>
      <button type="button" class="glass-button" data-action="cancel" hidden>Cancel</button>
      <button type="button" class="glass-button" data-action="log" aria-expanded="false">Run log</button></div>
    <section class="studio-drawer studio-log" aria-label="Run log" hidden><h2>Run log</h2><ol></ol></section>
    <dialog class="studio-research" aria-labelledby="studio-research-heading">
      <header><h2 id="studio-research-heading">Reference research</h2>
      <button type="button" class="secondary" data-research-close title="Close this view and let the agent keep running">Close view</button></header>
      <p class="fine" role="status" data-research-notice></p>
      <div data-research-body></div>
    </dialog>
    </section>`;
  const find = selector => root.querySelector(selector);
  const toolbar = find('.studio-bar');
  toolbar.prepend(name.closest('.studio-heading'));
  const viewport = find('.studio-viewport'), world = find('.studio-world'), nodes = find('.studio-nodes');
  const wires = find('.studio-wires'), reroutes = find('.studio-reroutes'), inspector = find('.studio-inspector'), library = find('.studio-library');
  const search = library.querySelector('input'), matches = find('.studio-matches'), progress = find('progress');
  const status = find('.studio-status output');
  const action = key => find(`[data-action="${key}"]`);
  const byId = id => graph.nodes.find(node => node.id === id);
  const runs = createStudioRuns(() => graph, () => { persist(true); renderNodes(); renderInspector(); }, report, () => sourceCatalog);
  const openResearch = createReferenceResearch(find('.studio-research'), {
    escape: esc, format, apply: applyResearch, message: value => { status.textContent = value; },
  });

  function persist(keepRemoval = false) {
    if (!keepRemoval) removedNode = null;
    action('undo-remove').hidden = !removedNode;
    const entries = [...runs.results.entries()].map(([id, {job, key}]) => [id, {job, key}]);
    try { localStorage.setItem(storageKey, JSON.stringify({graph, runs: entries})); }
    catch { status.textContent = 'Browser storage unavailable. Export the workflow to keep it.'; }
  }

  function title(node) {
    return operations[node.type].title;
  }

  function valueFor(node) {
    const target = node.type === 'viewer' ? runs.upstream(node, 'phase') : node;
    return target && runs.results.get(target.id);
  }

  function rawPhaseSet(node) {
    const source = runs.upstream(node, 'phase');
    return source && runs.results.get(source.id)?.result.phase_set;
  }

  function note(node) {
    const stored = valueFor(node);
    const current = stored && runs.current(node.type === 'viewer' ? runs.upstream(node, 'phase') : node);
    const recent = messages.get(node.id);
    if (recent?.state === 'running' || recent?.state === 'failed') return recent;
    if (Object.hasOwn(fileKinds, node.type)) {
      const input = runs.sourceInput(node, fileKinds[node.type][0]);
      return input.issue ? {text: input.issue, state: 'blocked'} : {text: input.name};
    }
    const issue =
      node.type === 'schedule' ? scheduleIssue(node.settings) :
      operations[node.type].run || node.type === 'viewer' || node.type === 'phaseData' ? runs.inputIssue(node) : null;
    if (issue) return {text: issue, state: 'blocked'};
    if (stored && !current) return {text: 'Stale result', state: 'stale'};
    if (current) {
      const result = current.result;
      if (node.type === 'density') {
        const density = result.properties?.density;
        return density?.state === 'estimated' ? {text: `${format(density.value_g_cm3)} g/cm³`, state: 'complete'}
          : {text: `${format(100 * (result.properties?.density_coverage_mole_fraction || 0))} mol% covered · Phase data needed`, state: 'coverage'};
      }
      if (node.type === 'tracer') return result.kawin.state === 'completed'
        ? {text: `${result.kawin.phase} · ${format(result.kawin.temperature_k)} K${result.kawin.reference_only ? ' · reference only' : ''}`, state: 'complete'}
        : {text: 'Unavailable · inspect inputs', state: 'unavailable'};
      const set = result.phase_set || result.final;
      const count = set.phases.length;
      if (node.type === 'phaseAssignment') {
        const unresolved = set.phases.filter(phase => !phase.reference && phase.phase_data?.state !== 'applicable').length;
        if (unresolved) return {text: `${unresolved} of ${count} phases need reference data`, state: 'coverage'};
      }
      return {text: `${count} ${count === 1 ? 'phase' : 'phases'} · ${format(set.temperature_k)} K`, state: 'complete'};
    }
    if (node.type === 'phaseData') return {text: [node.settings.materialId, node.settings.name].filter(Boolean).join(' · ')};
    return {text: ''};
  }

  function renderNodes() {
    name.textContent = graph.name;
    const existing = new Set([...nodes.children].map(element => element.dataset.node));
    nodes.innerHTML = graph.nodes.map(node => {
      const operation = operations[node.type];
      const variable = variableKinds[node.type];
      const fields = inlineFields(node);
      const pinRows = (io, direction) => Object.entries(io || {}).map(([key, pin]) => {
        const connected = graph.edges.some(edge => direction === 'output' ? edge[0] === node.id && edge[1] === key : edge[2] === node.id && edge[3] === key);
        return `<button type="button" class="studio-pin ${direction}${connected ? ' connected' : ''}${variable ? ' studio-variable-port' : ''}" data-pin="${key}"
          data-direction="${direction}" data-type="${pin.type}"
          aria-label="${esc(`${title(node)} ${pin.label} ${direction}`)}"><i aria-hidden="true"></i>${variable ?
            `<span class="visually-hidden">${pin.label}</span>` : pin.label}</button>`;
      }).join('');
      const connected = graph.edges.some(edge => edge[0] === node.id || edge[2] === node.id);
      const attributes = `data-node="${node.id}" data-group="${operation.group}" style="left:${node.x}px;top:${node.y}px"`;
      const classes = `studio-node${connected ? '' : ' detached'}${existing.has(node.id) ? '' : ' introduced'}`;
      if (variable) return `<article class="${classes} studio-variable" ${attributes} data-type="${Object.values(operation.outputs)[0].type}">
        <header><button type="button" class="studio-title" data-title>
          <span class="studio-variable-kind">${variable}</span><span class="studio-node-note"></span>
        </button></header>
        ${pinRows(operation.outputs, 'output')}
      </article>`;
      const configured = node.type === 'schedule' ? `<button type="button" class="studio-schedule-preview" data-edit-schedule aria-label="Edit processing schedule">
          <svg class="thermal-plot" role="img" aria-label="Planned temperature by event"></svg>
          <span>Edit schedule</span></button>` : '';
      const phases = node.type === 'phaseAssignment' ? rawPhaseSet(node)?.phases || graph.edges
        .filter(edge => edge[2] === node.id && inputPort(node, edge[3])?.type === 'phase-record')
        .map(edge => ({instance_id: edge[3], label: byId(edge[0]).settings.name || 'Configured Phase Data'})) : [];
      const phaseRows = node.type === 'phaseAssignment' ? `<div class="studio-phase-lines">
        ${phases.length ? phases.slice(0, 5).map(phase => {
          const key = phase.instance_id;
          const connected = Boolean(runs.upstream(node, key));
          return `<button type="button" class="studio-pin input${connected ? ' connected' : ''}" data-pin="${key}"
            data-direction="input" data-type="phase-record" aria-label="Phase Data input for ${esc(phase.label)}">
            <i aria-hidden="true"></i>${esc(phase.label)}</button>`;
        }).join('') : '<p class="fine">Run equilibrium to list phases.</p>'}
        ${phases.length > 5 ? `<button type="button" class="studio-pin input studio-more-phases" data-phase-overflow data-type="phase-record">
          <i aria-hidden="true"></i>+${phases.length - 5} in Inspector</button>` : ''}
      </div>` : '';
      return `<article class="${classes}" ${attributes}>
        <header><button type="button" class="studio-title" data-title>${esc(title(node))}</button>${operation.run ?
          `<button type="button" class="studio-play" aria-label="Run ${esc(title(node))}" data-play>▶</button>` : ''}</header>
        ${fields ? `<div class="studio-inline-fields" data-inline="${node.type}">${fields}</div>` : ''}
        ${configured}
        <div class="studio-pins">${pinRows(operation.inputs, 'input')}${phaseRows}${pinRows(operation.outputs, 'output')}</div>
        <p class="studio-node-note" ${fields ? 'hidden' : ''}></p><div class="studio-node-rail" hidden><span></span></div></article>`;
    }).join('');
    renderReroutes();
    for (const plot of nodes.querySelectorAll('.studio-schedule-preview svg')) {
      const node = byId(plot.closest('[data-node]').dataset.node);
      renderSchedulePlot(plot, schedulePoints(node.settings), {compact: true});
    }
    refreshPinHints();
    refreshStatuses();
    draw();
  }

  function renderReroutes() {
    reroutes.innerHTML = graph.edges.flatMap(([from, output, to, input, route = []], index) => {
      if (!wireInput(to, input)) return [];
      const port = operations[byId(from).type].outputs[output];
      return route.map((_, pointIndex) => `<button type="button" class="studio-reroute" data-wire="${index}"
        data-route-point="${pointIndex}" data-type="${port.type}"
        aria-label="Reroute point ${pointIndex + 1} on ${port.label}" title="Drag to reroute · right-click to remove point"></button>`);
    }).join('');
  }

  function refreshStatuses() {
    for (const element of nodes.children) {
      const node = byId(element.dataset.node);
      const value = note(node), label = element.querySelector('.studio-node-note');
      element.classList.toggle('selected', node.id === selected);
      const titleButton = element.querySelector('[data-title]');
      titleButton.setAttribute('aria-pressed', String(node.id === selected));
      if (element.classList.contains('studio-variable')) {
        titleButton.setAttribute('aria-label', [title(node), value.text].filter(Boolean).join(' · '));
        label.title = value.text;
      }
      label.textContent = value.text;
      label.hidden = !value.text;
      label.dataset.status = value.state || 'ready';
      const play = element.querySelector('[data-play]');
      if (play) play.disabled = busy;
      for (const control of element.querySelectorAll('[data-field]')) control.disabled = busy;
      const rail = element.querySelector('.studio-node-rail');
      if (rail) {
        rail.hidden = !Number.isFinite(value.percent);
        if (!rail.hidden) rail.firstElementChild.style.width = `${value.percent}%`;
      }
    }
    action('run').disabled = busy;
    action('cancel').hidden = !busy;
    action('undo-remove').disabled = busy;
    for (const control of inspector.querySelectorAll('[data-field], [data-source-file], [data-disconnect], [data-remove], [data-mp-phase], [data-add-phase-data], [data-owner], fieldset')) {
      control.disabled = busy;
    }
    for (const key of ['starter', 'blank']) action(key).disabled = busy;
    find('[data-open-graph]').disabled = busy;
    updateInspectorState();
    draw();
  }

  function updateInspectorState() {
    const badge = inspector.querySelector('[data-inspector-state]');
    const node = byId(selected);
    if (!badge || !node) return;
    const value = note(node);
    const state = value.state || 'ready';
    badge.dataset.status = state;
    badge.textContent = {complete: 'Complete', failed: 'Error', stale: 'Stale', unavailable: 'Unavailable', blocked: 'Needs input', coverage: 'Missing data',
      running: 'Running', ready: 'Ready'}[state];
    const issue = inspector.querySelector('[data-input-issue]');
    issue.hidden = state !== 'blocked';
    issue.textContent = state === 'blocked' ? value.text : '';
  }

  function renderInspector() {
    scheduleEditor?.dispose();
    scheduleEditor = null;
    const node = byId(selected);
    if (!node) {
      inspector.innerHTML = `<div class="studio-inspector-heading"><h2>Inspector</h2></div>
        <section class="studio-inspector-card"><p class="fine">Select a node.</p>${nodeList()}</section>`;
      return;
    }
    const result = valueFor(node);
    const target = node.type === 'viewer' ? runs.upstream(node, 'phase') : node;
    const inputs = graph.edges.filter(edge => edge[2] === node.id);
    const outgoing = graph.edges.filter(edge => edge[0] === node.id);
    const wiresMarkup = [...inputs, ...outgoing].map(edge => {
      const target = byId(edge[2]);
      const port = inputPort(target, edge[3]);
      const label = port.type === 'phase-record' ? rawPhaseSet(target)?.phases.find(p => p.instance_id === edge[3])?.label || port.label : port.label;
      return `<li>${esc(title(byId(edge[0])))} → ${esc(title(target))}
        <button type="button" class="secondary" data-disconnect="${graph.edges.indexOf(edge)}" ${busy ? 'disabled' : ''}>Disconnect ${esc(label)}</button></li>`;
    }).join('');
    const settings = settingsMarkup(node, sourceCatalog);
    const assignment = node.type === 'phaseAssignment' ? runs.current(node) : null;
    const missing = researchTargets(assignment?.result.phase_set).length;
    inspector.innerHTML = `<div class="studio-inspector-heading" data-group="${operations[node.type].group}">
        <h2 tabindex="-1">${esc(title(node))}</h2><span class="studio-badge" data-inspector-state></span></div>
      <p class="fine studio-warning" data-input-issue hidden></p>
      ${settings ? `<section class="studio-inspector-card studio-settings">${node.type === 'schedule' ? '' : '<h3>Inputs</h3>'}${settings}</section>` : ''}
      ${node.type === 'phaseAssignment' ? `<section class="studio-inspector-card"><h3>Phases</h3>
      ${assignment ? `<div class="studio-research-actions">${missing ?
        '<button type="button" class="secondary" data-research-start>Find missing data</button>' : ''}
        <button type="button" class="secondary" data-research-history>Reference research</button></div>` : ''}
      ${phaseAssignmentMarkup(node, rawPhaseSet(node), assignment?.result.phase_set, runs.upstream, esc, format)}</section>` : ''}
      ${result ? `<section class="studio-inspector-card studio-results"><h3>Result</h3>
      <p class="fine" data-stale ${runs.current(target) ? 'hidden' : ''}>Stale · values describe the previous run.</p>
      ${resultMarkup(node, result)}
      <button type="button" class="secondary" data-export-result>Export result JSON</button></section>` : ''}
      ${messages.get(node.id)?.state === 'failed' ? `<p class="error">${esc(messages.get(node.id).text)}</p>` : ''}
      <details><summary>Connections (${inputs.length + outgoing.length})</summary><ul>${wiresMarkup}</ul></details>
      <details><summary>Nodes (${graph.nodes.length})</summary>${nodeList()}</details>
      <button type="button" class="secondary studio-remove" data-remove ${busy ? 'disabled' : ''}>Remove node</button>`;
    updateInspectorState();
    if (node.type === 'schedule') {
      scheduleEditor = initProcessingEvents(values => editSchedule(node, values),
        {root: inspector, prefix: 'studio-', settings: node.settings, live: true});
      inspector.querySelector('.studio-schedule-options').addEventListener('input', event => {
        const {target} = event;
        editSchedule(node, {[target.dataset.scheduleOption]: target.valueAsNumber});
      });
    }
    if (busy) for (const control of inspector.querySelectorAll('[data-field], [data-source-file], [data-mp-phase], [data-add-phase-data], [data-owner], fieldset')) control.disabled = true;
    refreshPinHints();
  }

  function editSchedule(node, values) {
    if (busy) return;
    const next = Object.fromEntries(Object.entries(values).map(([key, value]) =>
      [key, key === 'events' ? restoreScheduleEvents(value) : Number.isNaN(value) ? null : value]));
    if (Object.entries(next).every(([key, value]) => JSON.stringify(node.settings[key]) === JSON.stringify(value))) return;
    Object.assign(node.settings, next);
    messages.clear();
    persist();
    inspector.querySelector('[data-cooling-controls]').hidden = node.settings.route !== 'arc_melting';
    const plot = nodes.querySelector(`[data-node="${node.id}"] .studio-schedule-preview svg`);
    renderSchedulePlot(plot, schedulePoints(node.settings), {compact: true});
    refreshStatuses();
  }

  function nodeList() {
    return graph.nodes.map(node => `<button type="button" data-select="${node.id}">${esc(title(node))}</button>`).join('');
  }

  function select(id) {
    selected = id;
    togglePanel('inspector', true);
    refreshStatuses();
    renderInspector();
  }

  function togglePanel(panel, visible) {
    const region = panel === 'inspector' ? inspector : find(`.studio-${panel}`);
    region.hidden = !(visible ?? region.hidden);
    action(panel).setAttribute('aria-expanded', String(!region.hidden));
    if (panel === 'inspector') find('.studio-body').classList.toggle('inspector-closed', region.hidden);
    draw();
  }

  function translate() {
    world.style.transform = `translate(${camera.x}px, ${camera.y}px) scale(${camera.scale})`;
    viewport.style.setProperty('--major-grid', `${100 * camera.scale}px`);
    viewport.style.setProperty('--minor-grid', `${20 * camera.scale}px`);
    viewport.style.setProperty('--grid-x', `${camera.x}px`);
    viewport.style.setProperty('--grid-y', `${camera.y}px`);
    world.style.setProperty('--reroute-scale', Math.max(1, 1 / camera.scale));
    draw();
  }

  function point(event) {
    const box = viewport.getBoundingClientRect();
    return {x: event.clientX - box.left, y: event.clientY - box.top};
  }

  function graphPoint(x, y) {
    return {x: (x - camera.x) / camera.scale, y: (y - camera.y) / camera.scale};
  }

  function fit() {
    if (!nodes.children.length || !viewport.clientWidth) return;
    const x = Math.min(...graph.nodes.map(node => node.x)), y = Math.min(...graph.nodes.map(node => node.y));
    const cards = [...nodes.children];
    const width = Math.max(...cards.map(el => byId(el.dataset.node).x + el.offsetWidth)) - x;
    const height = Math.max(...cards.map(el => byId(el.dataset.node).y + el.offsetHeight)) - y;
    const scale = Math.max(.25, Math.min(1.1, (viewport.clientWidth - 54) / width, (viewport.clientHeight - 52) / height));
    camera = {scale, x: (viewport.clientWidth - width * scale) / 2 - x * scale, y: (viewport.clientHeight - height * scale) / 2 - y * scale};
    translate();
  }

  function zoom(factor, x = viewport.clientWidth / 2, y = viewport.clientHeight / 2) {
    const scale = Math.max(.25, Math.min(2, camera.scale * factor));
    const ratio = scale / camera.scale;
    camera = {scale, x: x - (x - camera.x) * ratio, y: y - (y - camera.y) * ratio};
    translate();
  }

  function pinElement(id, key, direction) {
    return nodes.querySelector(`[data-node="${id}"] [data-pin="${key}"][data-direction="${direction}"]`);
  }

  function wireInput(id, key) {
    return pinElement(id, key, 'input') ||
      (inputPort(byId(id), key)?.type === 'phase-record' && rawPhaseSet(byId(id))?.phases.some(phase => phase.instance_id === key)
        ? nodes.querySelector(`[data-node="${id}"] [data-phase-overflow]`) : null);
  }

  const pinOwner = pin => pin.dataset.owner || pin.closest('[data-node]')?.dataset.node;
  const endpoint = pin => ({id: pinOwner(pin), pin: pin.dataset.pin, type: pin.dataset.type, direction: pin.dataset.direction});
  function wireBetween(first, second) {
    const [output, input] = first.direction === 'output' ? [first, second] : [second, first];
    return [output.id, output.pin, input.id, input.pin];
  }

  function pinCenter(element, bounds) {
    const pin = element.querySelector('i').getBoundingClientRect();
    return {x: (pin.left + pin.width / 2 - bounds.left) / camera.scale,
      y: (pin.top + pin.height / 2 - bounds.top) / camera.scale};
  }

  function refreshPinHints() {
    const from = gesture?.kind === 'wire' && gesture.moved ? gesture.origin : armed;
    for (const pin of root.querySelectorAll('[data-pin]')) {
      const target = endpoint(pin);
      const edge = from && from.direction !== target.direction && wireBetween(from, target);
      const compatible = Boolean(edge && !pin.hidden && accepts(graph, edge));
      const replaces = compatible && graph.edges.some(wire => wire[2] === edge[2] && wire[3] === edge[3] &&
        (wire[0] !== edge[0] || wire[1] !== edge[1]));
      pin.classList.toggle('armed', Boolean(from && from.direction === target.direction && from.id === target.id && from.pin === target.pin));
      pin.classList.toggle('compatible', compatible);
      pin.toggleAttribute('data-replaces', replaces);
      if (replaces) pin.setAttribute('aria-description', 'Replaces the existing connection');
      else pin.removeAttribute('aria-description');
    }
  }

  function wireTarget(event, target) {
    if (!target || (!viewport.contains(target) && !inspector.contains(target)) || target.closest('.studio-library')) return null;
    const direct = target.closest('[data-pin]');
    if (direct) return direct.classList.contains('compatible') ? direct : null;
    let nearest = null, distance = event.pointerType === 'touch' ? 26 : 18;
    for (const pin of nodes.querySelectorAll('.studio-pin.compatible')) {
      const icon = pin.querySelector('i').getBoundingClientRect();
      const x = icon.left + icon.width / 2, y = icon.top + icon.height / 2;
      const gap = Math.hypot(event.clientX - x, event.clientY - y);
      if (gap < distance && pin.contains(document.elementFromPoint(x, y))) {
        nearest = pin;
        distance = gap;
      }
    }
    return nearest;
  }

  function updateWireTarget(event) {
    const target = wireTarget(event, document.elementFromPoint(event.clientX, event.clientY));
    if (target === gesture.target) return;
    gesture.target?.classList.remove('snapped');
    gesture.target = target;
    target?.classList.add('snapped');
    status.textContent = target ? `${target.hasAttribute('data-replaces') ? 'Replace' : 'Connect'} ${target.textContent.trim()}` : gesture.status;
  }

  function draw() {
    if (drawFrame) return;
    drawFrame = requestAnimationFrame(() => {
      drawFrame = null;
      const bounds = world.getBoundingClientRect();
      const parts = graph.edges.map(([from, output, to, input, route = []], index) => {
        const a = pinElement(from, output, 'output'), b = wireInput(to, input);
        if (!a || !b) return '';
        const stops = [pinCenter(a, bounds), ...route, pinCenter(b, bounds)];
        const segments = stops.slice(1).map((end, segment) => wireSegment(stops[segment], end));
        return `<g data-type="${a.dataset.type}">
          <path class="studio-wire" d="${segments.join(' ')}"/>
          ${segments.map((segment, at) => `<path class="studio-wire-hit" data-wire="${index}" data-segment="${at}" d="${segment}"/>`).join('')}
        </g>`;
      });
      if (gesture?.kind === 'wire' && gesture.end) {
        const start = pinCenter(gesture.element, bounds);
        const end = gesture.target?.isConnected ? pinCenter(gesture.target, bounds) : graphPoint(gesture.end.x, gesture.end.y);
        const [a, b] = gesture.origin.direction === 'output' ? [start, end] : [end, start];
        parts.push(`<path class="studio-wire pending${gesture.target ? ' snapped' : ''}" data-type="${gesture.origin.type}"
          d="${wireSegment(a, b)}"/>`);
      }
      wires.innerHTML = parts.join('');
      for (const dot of reroutes.children) {
        const position = graph.edges[dot.dataset.wire][4][dot.dataset.routePoint];
        dot.style.left = `${position.x}px`;
        dot.style.top = `${position.y}px`;
      }
    });
  }

  function disconnect(index) {
    if (busy || !graph.edges[index]) return;
    graph.edges.splice(index, 1);
    messages.clear();
    persist(); renderNodes(); renderInspector();
  }

  function removeReroute(dot) {
    const edge = graph.edges[dot.dataset.wire];
    edge[4].splice(Number(dot.dataset.routePoint), 1);
    if (!edge[4].length) edge.pop();
    persist(); renderReroutes(); draw();
    viewport.focus({preventScroll: true});
  }

  function connect(edge) {
    if (busy || !accepts(graph, edge)) {
      status.textContent = 'Choose an input with the same data type.';
      return;
    }
    armed = null;
    const previous = graph.edges.find(wire => wire[2] === edge[2] && wire[3] === edge[3]);
    if (previous?.[0] !== edge[0] || previous?.[1] !== edge[1]) {
      graph.edges = graph.edges.filter(wire => wire !== previous);
      graph.edges.push(edge);
      messages.clear();
      persist();
      renderNodes();
    } else refreshPinHints();
    select(edge[2]);
    status.textContent = `Connected ${inputPort(byId(edge[2]), edge[3]).label}.`;
  }

  function removeNode() {
    const node = byId(selected);
    if (busy || !node || gesture) return;
    removedNode = {node, index: graph.nodes.indexOf(node), edges: graph.edges, result: runs.results.get(selected)};
    graph.nodes = graph.nodes.filter(item => item !== node);
    graph.edges = graph.edges.filter(edge => edge[0] !== selected && edge[2] !== selected);
    runs.results.delete(selected);
    messages.clear();
    selected = undefined;
    armed = null;
    persist(true); renderNodes(); renderInspector();
    status.textContent = `Removed ${title(node)}.`;
    viewport.focus({preventScroll: true});
  }

  function undoRemoval() {
    if (busy || !removedNode || gesture) return;
    const {node, index, edges, result} = removedNode;
    graph.nodes.splice(index, 0, node);
    graph.edges = edges;
    if (result) runs.results.set(node.id, result);
    messages.clear();
    persist(); renderNodes();
    select(node.id);
    nodes.querySelector(`[data-node="${node.id}"] [data-title]`).focus({preventScroll: true});
    status.textContent = `Restored ${title(node)}.`;
  }

  function openLibrary(x = 16, y = 16, from = null) {
    if (busy) return;
    menuState = {anchor: graphPoint(x, y), from};
    library.hidden = false;
    action('add').setAttribute('aria-expanded', 'true');
    search.value = '';
    filterLibrary();
    library.style.left = `${Math.max(7, Math.min(x, viewport.clientWidth - library.offsetWidth - 7))}px`;
    library.style.top = `${Math.max(7, Math.min(y, viewport.clientHeight - library.offsetHeight - 7))}px`;
    search.focus({preventScroll: true});
  }

  function closeLibrary(restoreFocus = false) {
    library.hidden = true;
    action('add').setAttribute('aria-expanded', 'false');
    menuState = null;
    if (restoreFocus) viewport.focus();
  }

  function filterLibrary() {
    const from = menuState?.from;
    const query = search.value.trim().toLowerCase();
    matches.innerHTML = Object.entries(operations).flatMap(([key, operation]) => {
      if (key === 'sources') return [];
      const ports = from ? Object.entries((from.direction === 'input' ? operation.outputs : operation.inputs) || {})
        .filter(([, port]) => port.type === from.type) : [['', null]];
      return (operation.title.toLowerCase().includes(query) || key.toLowerCase().includes(query))
        ? ports.map(([pin, port]) => `<button type="button" data-add="${key}" data-to-pin="${pin}">${operation.title}${port ? ` · ${port.label}` : ''}</button>`)
        : [];
    }).join('') || '<p class="fine">No matching nodes</p>';
  }

  function insert(button) {
    if (!menuState || busy || graph.nodes.length >= 200 || (menuState.from && graph.edges.length >= 500)) return;
    const {anchor, from} = menuState;
    const node = nodeOf(button.dataset.add, anchor.x, anchor.y);
    const direction = from?.direction === 'input' ? 'output' : 'input';
    const match = {id: node.id, pin: button.dataset.toPin, direction};
    const edge = from && wireBetween(from, match);
    if (edge && node.type === 'phaseData' && from.type === 'phase-record') seedPhaseData(node, byId(from.id), from.pin);
    graph.nodes.push(node);
    closeLibrary();
    if (edge && accepts(graph, edge)) {
      graph.edges = graph.edges.filter(wire => wire[2] !== edge[2] || wire[3] !== edge[3]);
      graph.edges.push(edge);
      messages.clear();
    }
    armed = null;
    renderNodes();
    const element = nodes.querySelector(`[data-node="${node.id}"]`);
    const ideal = {...anchor};
    if (edge) {
      const pin = pinCenter(pinElement(node.id, match.pin, match.direction), element.getBoundingClientRect());
      ideal.x -= pin.x;
      ideal.y -= pin.y;
    }
    placeNode(node, ideal);
  }

  function placeNode(node, ideal) {
    const element = nodes.querySelector(`[data-node="${node.id}"]`);
    const obstacles = [...nodes.children].filter(peer => peer !== element).map(peer => ({
      x: peer.offsetLeft, y: peer.offsetTop, width: peer.offsetWidth, height: peer.offsetHeight,
    }));
    const start = graphPoint(8, 8), end = graphPoint(viewport.clientWidth - 8, viewport.clientHeight - 8);
    const position = nearestPosition(ideal, {width: element.offsetWidth, height: element.offsetHeight}, obstacles,
      {left: start.x, top: start.y, right: end.x, bottom: end.y});
    Object.assign(node, position || ideal);
    element.style.left = `${node.x}px`;
    element.style.top = `${node.y}px`;
    persist();
    select(node.id);
    element.querySelector('[data-title]').focus({preventScroll: true});
  }

  function addPhaseData(assignment, key) {
    if (busy || graph.nodes.length >= 200 || graph.edges.length >= 500) return;
    if (runs.upstream(assignment, key)) return;
    const ideal = {x: assignment.x - 284, y: assignment.y + 212};
    const node = nodeOf('phaseData', ideal.x, ideal.y);
    if (!seedPhaseData(node, assignment, key)) return;
    graph.nodes.push(node);
    graph.edges.push([node.id, 'data', assignment.id, key]);
    armed = null;
    renderNodes();
    placeNode(node, ideal);
  }

  function seedPhaseData(node, assignment, key) {
    const set = rawPhaseSet(assignment);
    const phase = set?.phases.find(phase => phase.instance_id === key);
    if (!phase) return false;
    Object.assign(node.settings, {name: phase.label, temperature_k: String(set.temperature_k), pressure_pa: String(set.pressure_pa),
      composition_mole_fraction: JSON.stringify(phase.composition)});
    return true;
  }

  function beginResearch(phase, recent) {
    const node = byId(selected);
    const parent = node?.type === 'phaseAssignment' && runs.upstream(node, 'phase');
    const assignment = parent && runs.current(node);
    const equilibrium = parent && runs.current(parent);
    if (!assignment || !equilibrium || busy) return;
    persist(true);
    void openResearch({project_id: graph.researchProject, assignment_node: node.id, equilibrium_job: equilibrium.job,
      assignment_job: assignment.job, targets: researchTargets(assignment.result.phase_set)}, phase, recent);
  }

  async function applyResearch(anchor, submit, rerun, close) {
    const assignment = byId(anchor.assignment_node);
    const validTarget = () => {
      const parent = assignment && runs.upstream(assignment, 'phase');
      return !busy && graph.researchProject === anchor.project_id && byId(anchor.assignment_node) === assignment &&
        assignment?.type === 'phaseAssignment' && parent && runs.current(parent)?.job === anchor.equilibrium_job;
    };
    if (!validTarget()) throw new Error('The graph changed. Return to the current phase assignment.');
    const approved = await submit();
    if (!validTarget()) throw new Error('The graph changed while reviewing the proposals.');
    const updated = structuredClone(graph);
    for (const {phase_id, data} of approved.records) {
      const wire = updated.edges.find(edge => edge[2] === assignment.id && edge[3] === phase_id);
      const existing = wire && updated.nodes.find(node => node.id === wire[0]);
      const shared = existing && updated.edges.filter(edge => edge[0] === existing.id).length > 1;
      let node = existing;
      if (!node || shared) {
        if (updated.nodes.length >= 200 || (!wire && updated.edges.length >= 500)) {
          throw new Error('The graph has reached its node or connection limit.');
        }
        node = nodeOf('phaseData', assignment.x - 285, Math.min(10000, assignment.y + 214 + 96 *
          updated.edges.filter(edge => edge[2] === assignment.id && edge[1] === 'data').length));
        if (shared) node.settings = structuredClone(existing.settings);
        updated.nodes.push(node);
        if (wire) wire[0] = node.id;
        else updated.edges.push([node.id, 'data', assignment.id, phase_id]);
      }
      mergeResearchPhaseData(node.settings, data);
    }
    graph = updated;
    messages.clear();
    persist(true);
    close();
    renderNodes();
    renderInspector();
    status.textContent = 'Phase Data applied';
    if (rerun) {
      const currentAssignment = byId(assignment.id);
      const properties = graph.nodes.filter(node => node.type === 'density' &&
        runs.upstream(node, 'phase')?.id === assignment.id);
      await runTargets([currentAssignment, ...properties], false);
    }
  }

  function report(node, message, percent, failed = false) {
    status.textContent = `${title(node)} · ${message}`;
    progress.hidden = !busy;
    if (Number.isFinite(percent)) progress.value = percent;
    else progress.removeAttribute('value');
    const state = failed ? 'failed' : percent === 100 ? 'complete' : message === 'Canceled' ? 'canceled' : 'running';
    messages.set(node.id, {text: message, state, percent});
    if (logEntries.at(-1) !== status.textContent) {
      logEntries = [...logEntries.slice(-39), status.textContent];
      find('.studio-log ol').innerHTML = logEntries.map(entry => `<li>${esc(entry)}</li>`).join('');
    }
    refreshStatuses();
  }

  async function run(target) {
    if (busy) return;
    const targets = target ? [target] : graph.nodes.filter(node => operations[node.type].run && graph.edges.some(edge => edge[2] === node.id));
    await runTargets(targets, Boolean(target));
  }

  async function runTargets(targets, force) {
    if (!targets.length) { status.textContent = 'Connect a calculation node to run the graph.'; return; }
    busy = true;
    closeLibrary();
    refreshStatuses();
    try { await runs.run(targets, force); }
    finally { busy = false; progress.hidden = true; refreshStatuses(); renderInspector(); }
  }

  function setGraph(next) {
    if (busy) return;
    next.researchProject ||= crypto.randomUUID();
    graph = next;
    selected = graph.nodes[0]?.id;
    armed = null;
    closeLibrary();
    runs.results.clear();
    messages.clear();
    persist();
    renderNodes();
    renderInspector();
    fit();
    status.textContent = 'Ready';
  }

  function download(filename, value) {
    const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], {type: 'application/json'}));
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function openFile(file) {
    if (!file || busy) return;
    try {
      if (file.size > 1024 * 1024) throw new Error('Choose a workflow file of at most 1 MiB.');
      const value = JSON.parse(await file.text());
      if (value.format !== 'rutile' || value.schema_version !== 1 || value.kind !== 'workflow') throw new Error('Choose a Rutile workflow.');
      setGraph(restoreGraph(value.payload));
    } catch (error) { status.textContent = error.message; }
  }

  async function uploadFile(node, file) {
    if (!file) return;
    try {
      if (file.size > 10 * 1024 * 1024) throw new Error('Choose a file of at most 10 MiB.');
      const role = fileKinds[node.type][0];
      const content = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.split(',')[1]);
        reader.onerror = () => reject(new Error('Cannot read this file.'));
        reader.readAsDataURL(file);
      });
      const path = role === 'assessment' ? '/api/databases' : `/api/workflow/sources/${role}`;
      const data = await studioPost(path, {filename: file.name, encoding: 'base64', content});
      if (busy || byId(node.id) !== node) return;
      node.settings.file = {id: data.id, name: data.name || file.name};
      node.settings.preset = '';
      messages.clear();
      persist(); renderNodes(); renderInspector();
      status.textContent = `Imported ${file.name}`;
    } catch (error) { status.textContent = error.message; }
  }

  root.addEventListener('click', async event => {
    const button = event.target.closest('button');
    if (!button || suppressClick) return;
    const node = byId(pinOwner(button));
    if (button.hasAttribute('data-title')) select(node.id);
    else if (button.hasAttribute('data-edit-schedule')) {
      select(node.id);
      inspector.querySelector('h2').focus();
    } else if (button.hasAttribute('data-play')) { select(node.id); await run(node); }
    else if (button.hasAttribute('data-phase-overflow')) select(node.id);
    else if (button.dataset.addPhaseData) addPhaseData(byId(selected), button.dataset.addPhaseData);
    else if (button.hasAttribute('data-research-start') || button.hasAttribute('data-research-history') ||
        button.dataset.researchPhase) beginResearch(button.dataset.researchPhase, button.hasAttribute('data-research-history'));
    else if (button.dataset.pin && !busy) {
      const target = endpoint(button);
      if (armed && armed.direction !== target.direction) connect(wireBetween(armed, target));
      else {
        if (target.type === 'phase-record' && target.direction === 'input' && !button.dataset.owner) select(node.id);
        armed = target;
        refreshPinHints();
        status.textContent = `Choose a matching ${target.direction === 'input' ? 'output' : 'input'}, or open Add node.`;
      }
    } else if (button.dataset.add) insert(button);
    else if (button.dataset.select) {
      const target = byId(button.dataset.select);
      camera.x = 26 - target.x * camera.scale;
      camera.y = 26 - target.y * camera.scale;
      translate();
      select(target.id);
      nodes.querySelector(`[data-node="${target.id}"] [data-title]`).focus({preventScroll: true});
    } else if (button.dataset.disconnect !== undefined && !busy) {
      disconnect(Number(button.dataset.disconnect));
    } else if (button.hasAttribute('data-remove')) {
      removeNode();
    } else if (button.hasAttribute('data-export-result')) {
      const result = valueFor(byId(selected));
      if (result) download('rutile-node-result.json', result.result);
    } else {
      const key = button.dataset.action;
      if (['project', 'inspector', 'log'].includes(key)) togglePanel(key);
      else if (key === 'undo-remove') undoRemoval();
      else if (key === 'add') { if (library.hidden) openLibrary(viewport.clientWidth * .45, 16, armed); else closeLibrary(); }
      else if (key === 'fit') fit();
      else if (key === 'zoom-in') zoom(1.25);
      else if (key === 'zoom-out') zoom(.8);
      else if (key === 'run') await run();
      else if (key === 'cancel') {
        try { await runs.cancel(); } catch (error) { status.textContent = error.message; }
      } else if (key === 'starter' || key === 'blank') {
        setGraph(key === 'starter' ? starter() : {version: 3, name: 'Untitled workflow', nodes: [], edges: []});
        togglePanel('project', false);
      } else if (key === 'save') {
        download('alloy-workflow.rutile', {format: 'rutile', schema_version: 1, kind: 'workflow',
          document_id: crypto.randomUUID(), created_at_utc: new Date().toISOString(), name: graph.name, payload: graph, attachments: []});
      }
    }
  });

  root.addEventListener('change', event => {
    const control = event.target;
    if (control.hasAttribute('data-open-graph')) { void openFile(control.files[0]); control.value = ''; return; }
    const card = control.closest('[data-node]');
    const node = byId(card?.dataset.node ?? selected);
    if (!node || busy) return;
    if (control.hasAttribute('data-source-file')) { void uploadFile(node, control.files[0]); return; }
    if (node.type === 'phaseAssignment' && control.dataset.mpPhase) {
      const key = control.dataset.mpPhase;
      const id = control.value.trim().toLowerCase();
      if (id) node.settings.materialIds[key] = id;
      else delete node.settings.materialIds[key];
      control.value = id;
      control.setAttribute('aria-invalid', String(Boolean(id) && !materialId.test(id)));
      messages.clear(); persist(); refreshStatuses();
      return;
    }
    if (!control.dataset.field) return;
    const key = control.dataset.field;
    if (node.type === 'phaseData') {
      removeEditedResearch(node.settings, key);
      node.settings[key] = control.value;
      messages.clear(); persist(); refreshStatuses();
      return;
    }
    if (control.type === 'number' && (!Number.isFinite(control.valueAsNumber) || !control.validity.valid)) {
      control.value = node.settings[key];
      const label = control.labels[0]?.textContent.trim() || 'Value';
      status.textContent = control.min && control.max
        ? `${label} · enter a number between ${control.min} and ${control.max}.` : `${label} · enter a number.`;
      return;
    }
    node.settings[key] = control.type === 'checkbox' ? control.checked : control.type === 'number' ? control.valueAsNumber : control.value;
    const filePreset = key === 'preset' && Object.hasOwn(fileKinds, node.type);
    if (filePreset) node.settings.file = null;
    messages.clear();
    persist();
    if (filePreset) {
      renderNodes(); renderInspector();
      inspector.querySelector(`[data-field="${key}"]`)?.focus({preventScroll: true});
    } else {
      const graphCard = nodes.querySelector(`[data-node="${node.id}"]`);
      const other = card ? (selected === node.id ? inspector : null) : graphCard;
      const peer = other?.querySelector(`[data-field="${key}"]`);
      if (peer) peer.value = control.value;
      const visibleForms = selected === node.id ? [graphCard, inspector] : [graphCard];
      for (const form of visibleForms) {
        const balance = form.querySelector('[data-balance]');
        if (balance) balance.textContent = balanceText(node.settings);
      }
      const inspected = byId(selected);
      const stale = inspector.querySelector('[data-stale]');
      if (stale && inspected) {
        const target = inspected.type === 'viewer' ? runs.upstream(inspected, 'phase') : inspected;
        stale.hidden = Boolean(target && runs.current(target));
      }
      refreshStatuses();
    }
  });

  viewport.addEventListener('contextmenu', event => {
    const dot = event.target.closest('.studio-reroute');
    const wire = event.target.closest('.studio-wire-hit');
    if (dot || wire) {
      event.preventDefault();
      if (dot) removeReroute(dot);
      else disconnect(Number(wire.dataset.wire));
      return;
    }
    if (event.target.closest('.studio-node, .studio-library')) return;
    event.preventDefault();
    const {x, y} = point(event);
    openLibrary(x, y, armed);
  });
  viewport.addEventListener('dblclick', event => {
    const wire = event.target.closest('.studio-wire-hit');
    if (!wire) return;
    const edge = graph.edges[wire.dataset.wire];
    const route = edge[4] ?? (edge[4] = []);
    if (route.length >= 100) return;
    const {x, y} = point(event);
    const click = graphPoint(x, y);
    const length = wire.getTotalLength();
    const step = length / 40;
    let nearest = 0, distance = Infinity;
    const measure = at => {
      const p = wire.getPointAtLength(at);
      const squared = (p.x - click.x) ** 2 + (p.y - click.y) ** 2;
      if (squared < distance) { distance = squared; nearest = at; }
    };
    for (let i = 0; i <= 40; i++) measure(i * step);
    const start = Math.max(0, nearest - step);
    const end = Math.min(length, nearest + step);
    for (let i = 0; i <= 16; i++) measure(start + (end - start) * i / 16);
    const p = wire.getPointAtLength(nearest);
    route.splice(Number(wire.dataset.segment), 0, {x: p.x, y: p.y});
    persist(); renderReroutes(); draw();
  });
  viewport.addEventListener('wheel', event => {
    if (event.target.closest('.studio-library, input, select')) return;
    event.preventDefault();
    const {x, y} = point(event);
    zoom(event.deltaY < 0 ? 1.12 : .89, x, y);
  }, {passive: false});
  root.addEventListener('pointerdown', event => {
    if (event.button !== 0 || gesture || event.target.closest('.studio-library, [data-play], [data-edit-schedule], .studio-wire-hit, input, select, label')) return;
    const dot = event.target.closest('.studio-reroute');
    const pin = event.target.closest('[data-pin]');
    if (!viewport.contains(event.target) && !pin?.dataset.owner) return;
    const node = byId(event.target.closest('[data-node]')?.dataset.node);
    const at = point(event);
    if (dot) {
      const route = graph.edges[dot.dataset.wire][4][dot.dataset.routePoint];
      gesture = {kind: 'reroute', route, at, x: route.x, y: route.y};
    } else if (pin && !busy) gesture = {kind: 'wire', origin: endpoint(pin), element: pin, at};
    else if (node && event.target.closest('header')) gesture = {kind: 'node', node, at, x: node.x, y: node.y};
    else if (!node) {
      if (!library.hidden) closeLibrary();
      gesture = {kind: 'pan', at, x: camera.x, y: camera.y};
    } else {
      if (!pin) {
        select(node.id);
        viewport.focus({preventScroll: true});
      }
      return;
    }
    gesture.pointer = event.pointerId;
  });
  root.addEventListener('pointermove', event => {
    if (gesture?.pointer !== event.pointerId) return;
    const at = point(event), dx = at.x - gesture.at.x, dy = at.y - gesture.at.y;
    if (!gesture.moved && Math.hypot(dx, dy) < 4) return;
    if (!gesture.moved) {
      gesture.moved = true;
      viewport.setPointerCapture(event.pointerId);
      if (gesture.kind === 'wire') {
        armed = null;
        gesture.status = `Choose a compatible ${gesture.origin.direction === 'input' ? 'output' : 'input'}.`;
        status.textContent = gesture.status;
        refreshPinHints();
      } else if (gesture.kind === 'node') select(gesture.node.id);
    }
    if (gesture.kind === 'wire') {
      gesture.end = at;
      updateWireTarget(event);
      draw();
    }
    else if (gesture.kind === 'reroute') {
      gesture.route.x = gesture.x + dx / camera.scale;
      gesture.route.y = gesture.y + dy / camera.scale;
      draw();
    }
    else if (gesture.kind === 'pan') {
      camera.x = gesture.x + dx; camera.y = gesture.y + dy;
      viewport.classList.add('panning');
      translate();
    } else {
      const {node} = gesture;
      node.x = gesture.x + dx / camera.scale; node.y = gesture.y + dy / camera.scale;
      const el = nodes.querySelector(`[data-node="${node.id}"]`);
      el.style.left = `${node.x}px`; el.style.top = `${node.y}px`;
      draw();
    }
  });
  function endGesture(event) {
    if (gesture?.pointer !== event.pointerId) return;
    const previous = gesture;
    gesture = null;
    viewport.classList.remove('panning');
    if (!previous.moved) return;
    suppressClick = true;
    setTimeout(() => { suppressClick = false; }, 0);
    if (previous.kind === 'node' || previous.kind === 'reroute') persist();
    if (previous.kind === 'wire') {
      previous.target?.classList.remove('snapped');
      status.textContent = 'Ready';
      if (event.type === 'pointerup') {
        const target = document.elementFromPoint(event.clientX, event.clientY);
        const pin = wireTarget(event, target);
        if (pin) connect(wireBetween(previous.origin, endpoint(pin)));
        else if (target?.closest('[data-pin]')) status.textContent = previous.status;
        else if (target && viewport.contains(target) && !target.closest('.studio-node, .studio-reroute, .studio-library')) {
          const {x, y} = point(event);
          openLibrary(x, y, previous.origin);
        }
      }
      refreshPinHints();
    }
    draw();
  }
  for (const event of ['pointerup', 'pointercancel', 'lostpointercapture']) viewport.addEventListener(event, endGesture);
  window.addEventListener('pointerup', endGesture);
  search.addEventListener('input', filterLibrary);
  root.addEventListener('keydown', event => {
    if (event.key === 'Enter' && event.target.matches('input[data-field]:not([type="checkbox"]), input[data-mp-phase], .studio-schedule-editor input[type="number"]')) {
      event.preventDefault();
      event.target.blur();
      return;
    }
    const dot = event.target.closest('.studio-reroute');
    const editing = event.target.closest('input, textarea, select, [contenteditable]');
    const key = event.key.toLowerCase();
    const direction = {ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1]}[event.key];
    if (dot && (direction || event.key === 'Delete' || event.key === 'Backspace')) {
      event.preventDefault();
      if (direction) {
        const route = graph.edges[dot.dataset.wire][4][dot.dataset.routePoint];
        const step = event.shiftKey ? 20 : 5;
        route.x += direction[0] * step;
        route.y += direction[1] * step;
        persist(); draw();
      } else removeReroute(dot);
    } else if (event.key === 'Escape' && gesture?.kind === 'wire' && gesture.moved) {
      event.preventDefault();
      viewport.releasePointerCapture(gesture.pointer);
    } else if (event.key === 'Escape' && (!library.hidden || armed)) {
      event.preventDefault(); armed = null; closeLibrary(true);
      refreshPinHints();
      status.textContent = 'Ready';
    } else if (!library.hidden && library.contains(event.target)) {
      const choices = [...matches.querySelectorAll('button')];
      const index = choices.indexOf(event.target);
      if (event.key === 'ArrowDown' && choices.length) { event.preventDefault(); choices[(index + 1) % choices.length].focus(); }
      else if (event.key === 'ArrowUp' && index >= 0) { event.preventDefault(); (choices[index - 1] || search).focus(); }
      else if (event.key === 'Enter' && event.target === search && choices.length) { event.preventDefault(); insert(choices[0]); }
    } else if (!editing && !dot && !busy && !gesture && (viewport.contains(event.target) || inspector.contains(event.target)) &&
        removedNode && key === 'z' && (event.ctrlKey || event.metaKey) && !event.shiftKey && !event.altKey) {
      event.preventDefault();
      undoRemoval();
    } else if (!editing && !dot && !busy && !gesture && selected && (viewport.contains(event.target) || inspector.contains(event.target)) &&
        !event.ctrlKey && !event.metaKey && !event.altKey && ['x', 'delete', 'backspace'].includes(key)) {
      event.preventDefault();
      removeNode();
    } else if (event.target === viewport) {
      const steps = {ArrowLeft: [30, 0], ArrowRight: [-30, 0], ArrowUp: [0, 30], ArrowDown: [0, -30]};
      if (Object.hasOwn(steps, event.key)) {
        event.preventDefault();
        camera.x += steps[event.key][0]; camera.y += steps[event.key][1]; translate();
      } else if (event.key === 'Enter') { event.preventDefault(); openLibrary(16, 16, armed); }
      else if (event.key === '+' || event.key === '-') zoom(event.key === '+' ? 1.25 : .8);
    }
  });
  viewport.addEventListener('dragover', event => { event.preventDefault(); });
  viewport.addEventListener('drop', event => { event.preventDefault(); void openFile(event.dataTransfer.files[0]); });
  nodes.addEventListener('animationend', draw);
  new ResizeObserver(draw).observe(viewport);
  renderNodes();
  renderInspector();
  return {
    mountBack(button) {
      toolbar.prepend(button);
    },
    open() {
      clearTimeout(entryTimer);
      inspector.classList.remove('entry-settled');
      entryTimer = setTimeout(() => inspector.classList.add('entry-settled'), 2050);
      if (opened) return;
      opened = true;
      requestAnimationFrame(fit);
      void studioApi('/api/processing/sources').then(value => {
        sourceCatalog = value;
        refreshStatuses();
        if (Object.hasOwn(fileKinds, byId(selected)?.type)) renderInspector();
      }).catch(() => {});
      if (saved.runs.length) {
        busy = true;
        refreshStatuses();
        void runs.restore(saved.runs).finally(() => { busy = false; renderNodes(); renderInspector(); });
      }
    },
  };
}
