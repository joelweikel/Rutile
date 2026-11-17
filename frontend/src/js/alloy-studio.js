import {accepts, families, nodeOf, operations, restoreGraph, starter} from './alloy-graph.js';
import {createStudioRuns, studioApi, studioPost} from './alloy-runs.js';
import {nearestPosition, wireSegment} from './alloy-layout.js';

const storageKey = 'rutile.alloy-studio.v1';
const esc = value => String(value ?? '').replace(/[&<>"']/g, character =>
  ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character]));
const format = value => Number(value).toLocaleString(undefined, {maximumSignificantDigits: 6});
const fileKinds = {
  assessmentFile: ['assessment', '.tdb,.tbd'], physicalFile: ['physical', '.pdb'], mobilityFile: ['mobility', '.ddb'],
};

function savedWorkspace() {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey));
    return {graph: restoreGraph(saved.graph), runs: Array.isArray(saved.runs) ? saved.runs.slice(0, 100) : []};
  } catch {
    return {graph: starter(), runs: []};
  }
}

function phaseTable(value) {
  return `<div class="studio-condition"><span>${format(value.final.temperature_k)} K</span>
    <span>${format(value.settings.pressure_pa)} Pa</span></div>
    <table><thead><tr><th>Phase</th><th>mol%</th><th>Composition (at%)</th></tr></thead><tbody>
    ${value.final.phases.map(phase => `<tr><td>${esc(phase.label)}</td><td>${format(phase.fraction * 100)}</td>
      <td>${Object.entries(phase.composition).map(([element, amount]) => `${esc(element)} ${format(amount * 100)}`).join('<br>')}</td></tr>`).join('')}
    </tbody></table><details><summary>Source and assumptions</summary><p>${esc(value.provenance.source_name)}</p>
    <code>${esc(value.provenance.source_sha256)}</code><ul>${value.assumptions.map(note => `<li>${esc(note)}</li>`).join('')}</ul></details>`;
}

function resultMarkup(node, saved) {
  if (!saved) return '';
  const result = saved.result;
  if (node.type === 'viewer' || node.type === 'equilibrium') return phaseTable(result);
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
      const detail = model?.state === 'estimated' ? `${format(model.value_g_cm3)} g/cm³ · MatCalc DP · ${model.mapping.mapping}`
        : phase.density_source || model?.reason || phase.reason || 'No applicable density reference';
      return `<li><strong>${esc(phase.label)}</strong><span>${esc(detail)}</span></li>`;
    }).join('')}</ul>`;
}

function selectField(settings, key, label, options) {
  return `<label><span>${label}</span><select data-field="${key}">${options.map(([value, title]) =>
    `<option value="${value}" ${value === settings[key] ? 'selected' : ''}>${title}</option>`).join('')}</select></label>`;
}

function balanceText(settings) {
  return `Balance · ${settings.base} ${format(100 - settings.amount)} ${settings.basis === 'mass' ? 'wt%' : 'at%'}`;
}

function inlineFields(node) {
  const settings = node.settings;
  const input = (key, label, type, attributes) => `<label><span>${label}</span>
    <input data-field="${key}" type="${type}" ${attributes} value="${esc(settings[key])}"></label>`;
  const temperature = (key, label, maximum) =>
    input(key, label, 'number', `step="any" min="273.15" max="${maximum}"`);
  if (node.type === 'composition') return selectField(settings, 'base', 'Base element', families.map(key => [key, key])) +
    input('element', 'Addition element', 'text', 'maxlength="2" spellcheck="false"') +
    input('amount', 'Addition (%)', 'number', 'step="any" min="0" max="100"') +
    selectField(settings, 'basis', 'Composition basis', [['mass', 'wt%'], ['atomic', 'at%']]) +
    `<output class="studio-balance" data-balance>${esc(balanceText(settings))}</output>`;
  if (node.type === 'schedule') return temperature('initial', 'Initial temperature (K)', 2500) +
    temperature('melt', 'Melt temperature (K)', 4000) + temperature('final', 'Cooling target (K)', 2500) +
    input('pressure', 'Pressure (Pa)', 'number', 'step="any" min="0" max="1000000000"') +
    input('points', 'Cooling points', 'number', 'min="3" max="61"');
  return '';
}

function settingsMarkup(node, sources, upstream) {
  const s = node.settings;
  const fields = inlineFields(node);
  if (fields) return fields;
  if (node.type === 'sources') {
    const preset = sources.find(source => source.family === s.family);
    const custom = upstream(node, 'assessment');
    return selectField(s, 'family', 'MatCalc family', families.map(key => [key, key])) +
      `<dl class="studio-source-files"><div data-type="assessment"><dt>Thermodynamic</dt><dd>${esc(custom ? custom.settings.file?.name || 'Choose a connected file' :
        preset ? preset.thermodynamic + (preset.available ? '' : ' · missing') : 'Bundled family preset')}</dd></div>
      <div data-type="mobility"><dt>Mobility</dt><dd>${esc(upstream(node, 'mobility')?.settings.file?.name ||
        (custom ? 'Connect a compatible Mobility File' : preset?.mobility ? preset.mobility + (preset.mobility_available ? '' : ' · missing') : 'Named family companion'))}</dd></div>
      <div data-type="physical"><dt>Physical data</dt><dd>${esc(upstream(node, 'physical')?.settings.file?.name || 'physical_data.pdb · configured source')}</dd></div></dl>`;
  }
  if (Object.hasOwn(fileKinds, node.type)) {
    return `<label>Choose source file<input type="file" data-source-file accept="${fileKinds[node.type][1]}"></label>
      ${s.file ? `<p>${esc(s.file.name)}</p><code>${esc(s.file.id)}</code>` : ''}`;
  }
  if (node.type === 'density') return `<label><input type="checkbox" data-field="references" ${s.references ? 'checked' : ''}> Use compatible reference volumes</label>
    <label><input type="checkbox" data-field="parentDensity" ${s.parentDensity ? 'checked' : ''}> Allow disordered parent density</label>`;
  return '';
}

export function initAlloyStudio(root) {
  const saved = savedWorkspace();
  let graph = saved.graph, selected = graph.nodes.find(node => node.type === 'composition')?.id;
  let busy = false, opened = false, sources = [], camera = {x: 24, y: 24, scale: 1};
  let gesture, armed, menuState, drawFrame, entryTimer, logEntries = [], suppressClick = false;
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
      <button type="button" class="glass-button" data-action="cancel" hidden>Cancel</button>
      <button type="button" class="glass-button" data-action="log" aria-expanded="false">Run log</button></div>
    <section class="studio-drawer studio-log" aria-label="Run log" hidden><h2>Run log</h2><ol></ol></section>
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
  const runs = createStudioRuns(() => graph, () => { persist(); refreshStatuses(); renderInspector(); }, report);

  function persist() {
    const entries = [...runs.results.entries()].map(([id, {job, key}]) => [id, {job, key}]);
    try { localStorage.setItem(storageKey, JSON.stringify({graph, runs: entries})); }
    catch { status.textContent = 'Browser storage unavailable. Export the workflow to keep it.'; }
  }

  function title(node) {
    return node.type === 'sources' ? `MatCalc ${node.settings.family[0]}${node.settings.family.slice(1).toLowerCase()}` : operations[node.type].title;
  }

  function valueFor(node) {
    const target = node.type === 'viewer' ? runs.upstream(node, 'phase') : node;
    return target && runs.results.get(target.id);
  }

  function note(node) {
    const stored = valueFor(node);
    const current = stored && runs.current(node.type === 'viewer' ? runs.upstream(node, 'phase') : node);
    const recent = messages.get(node.id);
    if (recent?.state === 'running' || recent?.state === 'failed') return recent;
    if (stored && !current) return {text: 'Stale result', state: 'stale'};
    if (current) {
      const result = current.result;
      if (node.type === 'density') {
        const density = result.properties?.density;
        return density?.state === 'estimated' ? {text: `${format(density.value_g_cm3)} g/cm³`, state: 'complete'}
          : {text: 'Unavailable · inspect coverage', state: 'unavailable'};
      }
      if (node.type === 'tracer') return result.kawin.state === 'completed'
        ? {text: `${result.kawin.phase} · ${format(result.kawin.temperature_k)} K${result.kawin.reference_only ? ' · reference only' : ''}`, state: 'complete'}
        : {text: 'Unavailable · inspect inputs', state: 'unavailable'};
      const count = result.final.phases.length;
      return {text: `${count} ${count === 1 ? 'phase' : 'phases'} · ${format(result.final.temperature_k)} K`, state: 'complete'};
    }
    if (node.type === 'sources') return {text: 'Thermodynamic, mobility, physical'};
    if (Object.hasOwn(fileKinds, node.type)) return {text: node.settings.file?.name || 'Choose a file'};
    return {text: graph.edges.some(edge => edge[2] === node.id) ? 'Ready to inspect inputs' : 'Connect inputs'};
  }

  function renderNodes() {
    name.textContent = graph.name;
    const existing = new Set([...nodes.children].map(element => element.dataset.node));
    nodes.innerHTML = graph.nodes.map(node => {
      const operation = operations[node.type];
      const fields = inlineFields(node);
      const pinRows = (io, direction) => Object.entries(io || {}).map(([key, pin]) => {
        const connected = graph.edges.some(edge => direction === 'output' ? edge[0] === node.id && edge[1] === key : edge[2] === node.id && edge[3] === key);
        return `<button type="button" class="studio-pin ${direction}${connected ? ' connected' : ''}" data-pin="${key}"
          data-direction="${direction}" data-type="${pin.type}" aria-label="${esc(`${title(node)} ${pin.label} ${direction}`)}"><i aria-hidden="true"></i>${pin.label}</button>`;
      }).join('');
      const connected = graph.edges.some(edge => edge[0] === node.id || edge[2] === node.id);
      return `<article class="studio-node${connected ? '' : ' detached'}${existing.has(node.id) ? '' : ' introduced'}" data-node="${node.id}" data-group="${operation.group}" style="left:${node.x}px;top:${node.y}px">
        <header><button type="button" class="studio-title" data-title>${esc(title(node))}</button>${operation.run ?
          `<button type="button" class="studio-play" aria-label="Run ${esc(title(node))}" data-play>▶</button>` : ''}</header>
        ${fields ? `<div class="studio-inline-fields" data-inline="${node.type}">${fields}</div>` : ''}
        <div class="studio-pins">${pinRows(operation.inputs, 'input')}${pinRows(operation.outputs, 'output')}</div>
        <p class="studio-node-note" ${fields ? 'hidden' : ''}></p><div class="studio-node-rail" hidden><span></span></div></article>`;
    }).join('');
    renderReroutes();
    refreshStatuses();
    draw();
  }

  function renderReroutes() {
    reroutes.innerHTML = graph.edges.flatMap(([from, output, , , route = []], index) => {
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
      element.querySelector('[data-title]').setAttribute('aria-pressed', String(node.id === selected));
      label.textContent = value.text;
      label.dataset.status = value.state || 'ready';
      const play = element.querySelector('[data-play]');
      if (play) play.disabled = busy;
      for (const control of element.querySelectorAll('[data-field]')) control.disabled = busy;
      const rail = element.querySelector('.studio-node-rail');
      rail.hidden = !Number.isFinite(value.percent);
      if (!rail.hidden) rail.firstElementChild.style.width = `${value.percent}%`;
    }
    action('run').disabled = busy;
    action('cancel').hidden = !busy;
    for (const control of inspector.querySelectorAll('input,select,[data-disconnect],[data-remove]')) control.disabled = busy;
    for (const key of ['starter', 'blank']) action(key).disabled = busy;
    find('[data-open-graph]').disabled = busy;
    updateInspectorState();
    draw();
  }

  function updateInspectorState() {
    const badge = inspector.querySelector('[data-inspector-state]');
    const node = byId(selected);
    if (!badge || !node) return;
    const state = note(node).state || 'ready';
    badge.dataset.status = state;
    badge.textContent = {complete: 'Complete', failed: 'Error', stale: 'Stale', unavailable: 'Unavailable',
      running: 'Running', ready: 'Ready'}[state];
  }

  function renderInspector() {
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
    const wiresMarkup = [...inputs, ...outgoing].map(edge => `<li>${esc(title(byId(edge[0])))} → ${esc(title(byId(edge[2])))}
      <button type="button" class="secondary" data-disconnect="${graph.edges.indexOf(edge)}" ${busy ? 'disabled' : ''}>Disconnect ${esc(operations[byId(edge[2]).type].inputs[edge[3]].label)}</button></li>`).join('');
    const settings = settingsMarkup(node, sources, runs.upstream);
    inspector.innerHTML = `<div class="studio-inspector-heading" data-group="${operations[node.type].group}">
        <h2>${esc(title(node))}</h2><span class="studio-badge" data-inspector-state></span></div>
      ${settings ? `<section class="studio-inspector-card studio-settings"><h3>Inputs</h3>${settings}</section>` : ''}
      ${result ? `<section class="studio-inspector-card studio-results"><h3>Result</h3>
      <p class="fine" data-stale ${runs.current(target) ? 'hidden' : ''}>Stale · values describe the previous run.</p>
      ${resultMarkup(node, result)}
      <button type="button" class="secondary" data-export-result>Export result JSON</button></section>` : ''}
      ${messages.get(node.id)?.state === 'failed' ? `<p class="error">${esc(messages.get(node.id).text)}</p>` : ''}
      <details><summary>Connections (${inputs.length + outgoing.length})</summary><ul>${wiresMarkup}</ul></details>
      <details><summary>Nodes (${graph.nodes.length})</summary>${nodeList()}</details>
      <button type="button" class="secondary studio-remove" data-remove ${busy ? 'disabled' : ''}>Remove node</button>`;
    updateInspectorState();
    if (busy) for (const control of inspector.querySelectorAll('input,select')) control.disabled = true;
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
    const width = Math.max(...graph.nodes.map(node => node.x + 224)) - x;
    const height = Math.max(...[...nodes.children].map(el => byId(el.dataset.node).y + el.offsetHeight)) - y;
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

  function pinCenter(element, bounds) {
    const pin = element.querySelector('i').getBoundingClientRect();
    return {x: (pin.left + pin.width / 2 - bounds.left) / camera.scale,
      y: (pin.top + pin.height / 2 - bounds.top) / camera.scale};
  }

  function draw() {
    if (drawFrame) return;
    drawFrame = requestAnimationFrame(() => {
      drawFrame = null;
      const bounds = world.getBoundingClientRect();
      const parts = graph.edges.map(([from, output, to, input, route = []], index) => {
        const a = pinElement(from, output, 'output'), b = pinElement(to, input, 'input');
        const stops = [pinCenter(a, bounds), ...route, pinCenter(b, bounds)];
        const segments = stops.slice(1).map((end, segment) => wireSegment(stops[segment], end));
        return `<g data-type="${a.dataset.type}">
          <path class="studio-wire" d="${segments.join(' ')}"/>
          ${segments.map((segment, at) => `<path class="studio-wire-hit" data-wire="${index}" data-segment="${at}" d="${segment}"/>`).join('')}
        </g>`;
      });
      if (gesture?.kind === 'wire' && gesture.end) {
        const a = pinElement(gesture.from, gesture.pin, 'output');
        parts.push(`<path class="studio-wire pending" data-type="${a.dataset.type}"
          d="${wireSegment(pinCenter(a, bounds), graphPoint(gesture.end.x, gesture.end.y))}"/>`);
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
    graph.edges = graph.edges.filter(previous => previous[2] !== edge[2] || previous[3] !== edge[3]);
    graph.edges.push(edge);
    messages.clear();
    armed = null;
    persist();
    renderNodes();
    select(edge[2]);
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
    const type = menuState?.from?.type;
    const query = search.value.trim().toLowerCase();
    matches.innerHTML = Object.entries(operations).flatMap(([key, operation]) => {
      const ports = type ? Object.entries(operation.inputs || {}).filter(([, port]) => port.type === type) : [['', null]];
      return (operation.title.toLowerCase().includes(query) || key.toLowerCase().includes(query))
        ? ports.map(([pin, port]) => `<button type="button" data-add="${key}" data-to-pin="${pin}">${operation.title}${port ? ` · ${port.label}` : ''}</button>`)
        : [];
    }).join('') || '<p class="fine">No matching nodes</p>';
  }

  function insert(button) {
    if (!menuState || busy || graph.nodes.length >= 100) return;
    const {anchor, from} = menuState;
    const node = nodeOf(button.dataset.add, anchor.x, anchor.y);
    const edge = from && [from.id, from.pin, node.id, button.dataset.toPin];
    graph.nodes.push(node);
    closeLibrary();
    if (edge && accepts(graph, edge)) graph.edges.push(edge);
    armed = null;
    renderNodes();
    const element = nodes.querySelector(`[data-node="${node.id}"]`);
    const ideal = {...anchor};
    if (edge) {
      const pin = pinCenter(pinElement(node.id, edge[3], 'input'), element.getBoundingClientRect());
      ideal.x -= pin.x;
      ideal.y -= pin.y;
    }
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
    if (!targets.length) { status.textContent = 'Connect a calculation node to run the graph.'; return; }
    busy = true;
    closeLibrary();
    refreshStatuses();
    try { await runs.run(targets, Boolean(target)); }
    finally { busy = false; progress.hidden = true; refreshStatuses(); renderInspector(); }
  }

  function setGraph(next) {
    if (busy) return;
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
      messages.clear();
      persist(); renderNodes(); renderInspector();
      status.textContent = `Imported ${file.name}`;
    } catch (error) { status.textContent = error.message; }
  }

  root.addEventListener('click', async event => {
    const button = event.target.closest('button');
    if (!button || suppressClick) return;
    const node = byId(button.closest('[data-node]')?.dataset.node);
    if (button.hasAttribute('data-title')) select(node.id);
    else if (button.hasAttribute('data-play')) { select(node.id); await run(node); }
    else if (button.dataset.pin && !busy) {
      if (button.dataset.direction === 'output') {
        armed = {id: node.id, pin: button.dataset.pin, type: button.dataset.type};
        for (const pin of nodes.querySelectorAll('.armed')) pin.classList.remove('armed');
        button.classList.add('armed');
        status.textContent = 'Choose a matching input, or open Add node.';
      } else if (armed) connect([armed.id, armed.pin, node.id, button.dataset.pin]);
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
    } else if (button.hasAttribute('data-remove') && !busy) {
      graph.nodes = graph.nodes.filter(item => item.id !== selected);
      graph.edges = graph.edges.filter(edge => edge[0] !== selected && edge[2] !== selected);
      runs.results.delete(selected);
      messages.clear();
      selected = undefined;
      armed = null;
      persist(); renderNodes(); renderInspector();
      viewport.focus();
    } else if (button.hasAttribute('data-export-result')) {
      const result = valueFor(byId(selected));
      if (result) download('rutile-node-result.json', result.result);
    } else {
      const key = button.dataset.action;
      if (['project', 'inspector', 'log'].includes(key)) togglePanel(key);
      else if (key === 'add') { if (library.hidden) openLibrary(viewport.clientWidth * .45, 16, armed); else closeLibrary(); }
      else if (key === 'fit') fit();
      else if (key === 'zoom-in') zoom(1.25);
      else if (key === 'zoom-out') zoom(.8);
      else if (key === 'run') await run();
      else if (key === 'cancel') {
        try { await runs.cancel(); } catch (error) { status.textContent = error.message; }
      } else if (key === 'starter' || key === 'blank') {
        setGraph(key === 'starter' ? starter() : {version: 1, name: 'Untitled workflow', nodes: [], edges: []});
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
    if (!control.dataset.field) return;
    const key = control.dataset.field;
    if (control.type === 'number' && (!Number.isFinite(control.valueAsNumber) || !control.validity.valid)) {
      control.value = node.settings[key];
      const label = control.labels[0]?.textContent.trim() || 'Value';
      status.textContent = control.min && control.max
        ? `${label} · enter a number between ${control.min} and ${control.max}.` : `${label} · enter a number.`;
      return;
    }
    node.settings[key] = control.type === 'checkbox' ? control.checked : control.type === 'number' ? control.valueAsNumber : control.value;
    messages.clear();
    persist();
    if (node.type === 'sources') {
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
  viewport.addEventListener('pointerdown', event => {
    if (event.button !== 0 || gesture || event.target.closest('.studio-library, [data-play], .studio-wire-hit, input, select, label')) return;
    const dot = event.target.closest('.studio-reroute');
    const pin = event.target.closest('[data-pin]');
    const node = byId(event.target.closest('[data-node]')?.dataset.node);
    const at = point(event);
    if (dot) {
      const route = graph.edges[dot.dataset.wire][4][dot.dataset.routePoint];
      gesture = {kind: 'reroute', route, at, x: route.x, y: route.y};
    } else if (pin?.dataset.direction === 'output' && !busy) gesture = {kind: 'wire', from: node.id, pin: pin.dataset.pin, type: pin.dataset.type, at};
    else if (node && event.target.closest('header')) gesture = {kind: 'node', node, at, x: node.x, y: node.y};
    else if (!node) {
      if (!library.hidden) closeLibrary();
      gesture = {kind: 'pan', at, x: camera.x, y: camera.y};
    } else return;
    gesture.pointer = event.pointerId;
  });
  viewport.addEventListener('pointermove', event => {
    if (gesture?.pointer !== event.pointerId) return;
    const at = point(event), dx = at.x - gesture.at.x, dy = at.y - gesture.at.y;
    if (!gesture.moved && Math.hypot(dx, dy) < 4) return;
    if (!gesture.moved) { gesture.moved = true; viewport.setPointerCapture(event.pointerId); }
    if (gesture.kind === 'wire') { gesture.end = at; draw(); }
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
    if (previous.kind === 'wire' && event.type === 'pointerup') {
      const target = document.elementFromPoint(event.clientX, event.clientY);
      const pin = target?.closest('[data-direction="input"]');
      if (pin) connect([previous.from, previous.pin, pin.closest('[data-node]').dataset.node, pin.dataset.pin]);
      else if (target && viewport.contains(target) && !target.closest('.studio-node, .studio-reroute')) {
        const {x, y} = point(event);
        openLibrary(x, y, {id: previous.from, pin: previous.pin, type: previous.type});
      }
    }
    draw();
  }
  for (const event of ['pointerup', 'pointercancel', 'lostpointercapture']) viewport.addEventListener(event, endGesture);
  window.addEventListener('pointerup', endGesture);
  search.addEventListener('input', filterLibrary);
  root.addEventListener('keydown', event => {
    if (event.key === 'Enter' && event.target.matches('input[data-field]:not([type="checkbox"])')) {
      event.preventDefault();
      event.target.blur();
      return;
    }
    const dot = event.target.closest('.studio-reroute');
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
    } else if (event.key === 'Escape' && (!library.hidden || armed)) {
      event.preventDefault(); armed = null; closeLibrary(true);
      for (const pin of nodes.querySelectorAll('.armed')) pin.classList.remove('armed');
    } else if (!library.hidden && library.contains(event.target)) {
      const choices = [...matches.querySelectorAll('button')];
      const index = choices.indexOf(event.target);
      if (event.key === 'ArrowDown' && choices.length) { event.preventDefault(); choices[(index + 1) % choices.length].focus(); }
      else if (event.key === 'ArrowUp' && index >= 0) { event.preventDefault(); (choices[index - 1] || search).focus(); }
      else if (event.key === 'Enter' && event.target === search && choices.length) { event.preventDefault(); insert(choices[0]); }
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
      void studioApi('/api/processing/sources').then(value => { sources = value.sources; renderInspector(); }).catch(() => {});
      if (saved.runs.length) {
        busy = true;
        refreshStatuses();
        void runs.restore(saved.runs).finally(() => { busy = false; refreshStatuses(); renderInspector(); });
      }
    },
  };
}
