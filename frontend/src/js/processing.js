import {initProcessingEvents} from './processing-events.js';

const defaultMeltC = {Mg: 800, Al: 800, Ti: 1900, Fe: 1700, Ni: 1600, Mo: 2900};

export const processingMarkup = `
  <div class="processing-layout">
    <figure class="thermal-chart">
      <figcaption><h3>Temperature schedule</h3><span class="fine">Event sequence</span></figcaption>
      <svg id="thermal-plot" role="img" aria-label="Planned temperature by processing event"></svg>
      <p class="fine" id="thermal-selection"></p>
    </figure>
    <section class="process-sequence" aria-labelledby="sequence-heading">
      <div class="sequence-heading"><h3 id="sequence-heading">Events</h3>
        <details class="process-add" id="process-add"><summary>+ Add event</summary>
          <div class="process-menu">
            <button type="button" data-add-event="temperature_change">Temperature change</button>
            <button type="button" data-add-event="anneal">Anneal</button>
            <details><summary>Quench</summary><div class="quench-menu">
              <button type="button" data-add-event="quench" data-medium="water">Water</button>
              <button type="button" data-add-event="quench" data-medium="oil">Oil</button>
              <button type="button" data-add-event="quench" data-medium="air">Air</button>
              <button type="button" data-add-event="quench" data-medium="brine">Brine</button>
            </div></details>
            <button type="button" data-add-event="cold_work">Cold work</button>
          </div>
        </details>
      </div>
      <label for="opt-route">Starting route</label>
      <select id="opt-route"><option value="arc_melting">Arc melt, then cool</option><option value="heat_treatment">Start with solid alloy</option></select>
      <details id="process-initial" class="process-event"><summary><span>Initial state</span><span class="event-value"></span></summary>
        <div class="event-fields"><div><label for="process-start-temperature">Initial temperature (°C)</label><input id="process-start-temperature" type="number" min="0" max="2226.85" step="any" value="25" required></div></div>
      </details>
      <details id="process-melting" class="process-event"><summary><span>Arc melt &amp; cool</span><span class="event-value"></span></summary>
        <div class="event-fields"><div><label for="process-melt-temperature">Melt temperature (°C)</label><input id="process-melt-temperature" type="number" min="0" max="3726.85" step="any" value="800" required></div>
        <div><label for="opt-temperature">Cool to (°C)</label><input id="opt-temperature" type="number" min="0" max="2226.85" step="any" value="25" required></div></div>
      </details>
      <div id="process-events"></div>
    </section>
  </div>
  <details class="advanced processing-settings" id="processing-settings"><summary>Source &amp; calculation settings</summary>
  <div class="two-col"><div><label for="process-source">Thermodynamic source</label><select id="process-source"><option value="">MatCalc family assessment</option></select><p class="fine" id="process-source-status" role="status"></p></div>
  <div><label for="opt-pressure">Pressure (Pa)</label><input id="opt-pressure" type="number" min="1" max="1000000000" step="any" value="101325" required></div></div>
  <div><label for="process-import">Import thermodynamic TDB</label><input id="process-import" type="file" accept=".tdb,.tbd"><p class="fine">Manual sources use their own equilibrium models.</p></div>
  <div id="process-phase-policy-field" hidden><label for="process-phase-policy">Phase selection</label><select id="process-phase-policy" aria-describedby="process-phase-policy-help" disabled><option value="fe_cementite">Plain-carbon steel (Fe–Fe₃C)</option><option value="all_compatible">All compatible phases</option></select><p id="process-phase-policy-help" class="fine">Metastable equilibrium with liquid, ferrite, austenite and cementite. Graphite is suspended.</p></div>
  <p id="process-steel-availability" class="fine" hidden>Fe–Fe₃C requires carbon as the sole addition and the default MatCalc Fe 2.062 source.</p>
  <label class="reference-toggle"><input id="process-physical-density" type="checkbox" checked> Use local MatCalc density parameters</label>
  <label class="reference-toggle"><input id="process-reference-properties" type="checkbox" checked> Use Materials Project density and elasticity references</label>
  <label class="reference-toggle"><input id="process-screening-properties" type="checkbox" checked> Allow screening estimates</label>
  </details>
  <details class="advanced"><summary>Notes</summary><label for="opt-condition-notes">Processing notes (optional)</label><textarea id="opt-condition-notes" rows="3" maxlength="2000"></textarea></details>`;

export function initProcessing(onChange, onElements = () => {}) {
  const $ = id => document.getElementById(id);
  let family = null, sourceInfo = null, meltEdited = false;
  let selectedAdditions = [];
  const phasePolicy = $('process-phase-policy');
  const schedule = initProcessingEvents(onChange);
  const imported = new Map();
  const sourceRequest = fetch('/api/processing/sources').then(async response => {
    const value = await response.json();
    if (!response.ok) throw new Error(value.detail || 'Sources unavailable.');
    sourceInfo = value.sources; updateSource();
  }).catch(() => { $('process-source-status').textContent = 'Source availability will be checked when you run.'; });
  function updatePhasePolicy() {
    const source = sourceInfo?.find(item => item.family === 'FE');
    const ironCarbon = family === 'Fe' && selectedAdditions.includes('C');
    const eligible = ironCarbon && selectedAdditions.length === 1 &&
      !$('process-source').value && source?.steel_equilibrium_available;
    $('process-phase-policy-field').hidden = !eligible;
    $('process-steel-availability').hidden = !ironCarbon || eligible;
    phasePolicy.disabled = !eligible;
    $('process-phase-policy-help').textContent = phasePolicy.value === 'fe_cementite' ?
      'Metastable equilibrium with liquid, ferrite, austenite and cementite. Graphite is suspended.' :
      'Includes graphite and specialized MatCalc phase models.';
  }
  function updateSource() {
    const source = sourceInfo?.find(item => item.family === family?.toUpperCase());
    $('process-source').options[0].textContent = source ? source.thermodynamic : 'MatCalc family assessment';
    $('process-source-status').textContent = $('process-source').value ? 'Manual source · coverage unverified' : source ?
      `${source.available ? 'Available' : 'Unavailable — import a TDB'}${source.available && source.mobility_available ? ` · Mobility attached: ${source.mobility}` : ' · Mobility unavailable'} · assessment coverage unverified` : '';
    const elements = $('process-source').value ? imported.get($('process-source').value) : source?.elements;
    onElements(elements || null);
    updatePhasePolicy();
  }
  $('process-melt-temperature').addEventListener('input', () => { meltEdited = true; });
  $('process-source').addEventListener('change', updateSource);
  phasePolicy.addEventListener('change', updatePhasePolicy);
  $('process-import').addEventListener('change', async () => {
    const file = $('process-import').files[0];
    if (!file) return;
    $('process-import').disabled = true;
    try {
      if (file.size > 10 * 1024 * 1024) throw new Error('TDB upload limit is 10 MiB.');
      const bytes = new Uint8Array(await file.arrayBuffer());
      let binary = '';
      for (let i = 0; i < bytes.length; i += 8192) binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
      const response = await fetch('/api/databases', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({filename: file.name, content: btoa(binary), encoding: 'base64'})});
      const value = await response.json();
      if (!response.ok) throw new Error(value.detail || 'Import failed.');
      if (value.parse_error || !value.has_gibbs_energy) throw new Error(value.parse_error || 'This source has no Gibbs-energy data.');
      const option = new Option(file.name, value.id, true, true);
      imported.set(value.id, value.elements);
      $('process-source').add(option); updateSource(); onChange();
    } catch (error) { $('process-source-status').textContent = error.message; }
    finally { $('process-import').disabled = false; }
  });
  return {...schedule, setFamily(value) {
    family = value;
    if (!meltEdited) $('process-melt-temperature').value = defaultMeltC[family];
    updateSource(); schedule.redraw();
  }, setAdditions(elements) {
    selectedAdditions = elements;
    updatePhasePolicy();
  }, phasePolicy() {
    return phasePolicy.disabled ? 'all_compatible' : phasePolicy.value;
  }, async ready() { await sourceRequest; }, phaseSelection() {
    return phasePolicy.disabled ? null : phasePolicy.selectedOptions[0].textContent;
  }};
}
