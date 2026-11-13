// Arc melting is a homogeneous material-point equilibrium approximation.
export const processingMarkup = `
  <div class="processing-inputs two-col"><div><label for="opt-route">Processing route</label><select id="opt-route" required><option value="arc_melting">Arc melting</option></select></div><div><label for="process-source">Thermodynamic source</label><select id="process-source"><option value="">MatCalc family assessment</option></select><p class="fine" id="process-source-status" role="status"></p></div></div>
  <div><label for="process-import">Use another thermodynamic TDB</label><input id="process-import" type="file" accept=".tdb,.tbd"><p class="fine">A manual source uses its own equilibrium models; MatCalc mobility data is not attached automatically.</p></div>
  <div id="process-phase-policy-field" hidden><label for="process-phase-policy">Phase selection</label><select id="process-phase-policy" aria-describedby="process-phase-policy-help" disabled><option value="fe_cementite">Plain-carbon steel (Fe–Fe₃C)</option><option value="all_compatible">All compatible phases</option></select><p id="process-phase-policy-help" class="fine">Metastable equilibrium with liquid, ferrite, austenite and cementite. Graphite is suspended.</p></div>
  <p id="process-steel-availability" class="fine" hidden>Fe–Fe₃C requires carbon as the sole addition and the default MatCalc Fe 2.062 source.</p>
  <div class="two-col"><div><label for="process-start-temperature">Initial annealed equilibrium (°C)</label><input id="process-start-temperature" type="number" min="0" max="2226.85" step="any" value="25" required></div><div><label for="process-melt-temperature">Fully mixed melt temperature (°C)</label><input id="process-melt-temperature" type="number" min="0" max="3726.85" step="any" value="800" required></div><div><label for="opt-temperature">Final temperature (K)</label><input id="opt-temperature" type="number" min="273.15" max="2500" step="any" value="298.15" required></div><div><label for="opt-pressure">Pressure (Pa)</label><input id="opt-pressure" type="number" min="1" max="1000000000" step="any" value="101325" required></div></div>
  <p class="fine">Pure selected elements, no composition loss. Complete equilibrium is assumed throughout cooling; cooling rate and post-processing are not modeled.</p>
  <label class="reference-toggle"><input id="process-physical-density" type="checkbox" checked> Use local MatCalc density parameters where supported</label><p class="fine">Uses each phase’s composition and temperature. Unsupported models remain explicit; no API key is needed for local density.</p>
  <label class="reference-toggle"><input id="process-reference-properties" type="checkbox" checked> Estimate density and modulus with Materials Project</label><p class="fine">Bundled MatCalc crystal identities and compatible reference densities work offline. An API key enables stiffness tensor lookup.</p>
  <label class="reference-toggle"><input id="process-screening-properties" type="checkbox" checked> Allow screening estimates when alloy references are missing</label><p class="fine">Elemental modulus interpolation works offline for supported disordered phases. Materials Project can supply additional screening references.</p>
  <div class="thermal-chart"><svg id="thermal-plot" viewBox="0 0 600 230" role="img" aria-label="Arc melting equilibrium states"></svg></div>
  <details class="advanced"><summary>Notes</summary><label for="opt-condition-notes">Processing notes (optional)</label><textarea id="opt-condition-notes" rows="3" maxlength="2000"></textarea></details>`;

export function initProcessing(root, onChange, onElements = () => {}) {
  const $ = id => document.getElementById(id);
  let family = null, sourceInfo = null, meltEdited = false;
  let selectedAdditions = [];
  const phasePolicy = $('process-phase-policy');
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
  function redraw() {
    const start = Number($('process-start-temperature').value), melt = Number($('process-melt-temperature').value), end = Number($('opt-temperature').value) - 273.15;
    const minimum = Math.min(start, end) - 25, span = Math.max(100, melt - minimum + 25);
    const y = t => 170 - (t - minimum) / span * 140;
    const values = [start, melt, end], xs = [65, 300, 535];
    $('thermal-plot').innerHTML = `<title>Arc melting equilibrium states</title><text x="20" y="18">Temperature (°C)</text><polyline class="thermal-line" points="${values.map((t, i) => `${xs[i]},${y(t)}`).join(' ')}"/>${values.map((t, i) => `<circle cx="${xs[i]}" cy="${y(t)}" r="4"/><text x="${xs[i]}" y="${y(t)-12}" text-anchor="middle">${Number(t.toFixed(2))}</text><text x="${xs[i]}" y="205" text-anchor="middle">${['Annealed', 'Melt', 'Cooled'][i]}</text>`).join('')}`;
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
  root.addEventListener('input', redraw); root.addEventListener('change', redraw);
  redraw();
  return {redraw, readSchedule: () => [], setFamily(value) {
    family = value;
    if (!meltEdited) $('process-melt-temperature').value = {Al: 800, Fe: 1700, Ni: 1600}[family];
    updateSource(); redraw();
  }, setAdditions(elements) {
    selectedAdditions = elements;
    updatePhasePolicy();
  }, phasePolicy() {
    return phasePolicy.disabled ? 'all_compatible' : phasePolicy.value;
  }, async ready() { await sourceRequest; }, summary() { return {
    route: 'Arc melting · equilibrium cooling', start: Number($('process-start-temperature').value),
    melt: Number($('process-melt-temperature').value), end: Number($('opt-temperature').value),
    phaseSelection: phasePolicy.disabled ? null : phasePolicy.selectedOptions[0].textContent,
    events: [], work: 'None',
  }; }};
}
