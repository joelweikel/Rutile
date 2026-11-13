import {processingMarkup, initProcessing} from './processing.js';
import {initPhaseSimulation} from './phase-simulation.js';
// Phase simulation uses an explicit backend job. Property optimization remains planned.
const steps = ['Alloy family', 'Composition', 'Processing', 'Goals & limits', 'Review'];
const families = {Al: {name: 'Aluminum', source: 'MatCalc · mc_al_v2037'}, Fe: {name: 'Iron', source: 'MatCalc · mc_fe_v2062'}, Ni: {name: 'Nickel', source: 'MatCalc · mc_ni_v2036'}};
const additions = {Al: 'Aluminum', C: 'Carbon', Mo: 'Molybdenum', Nb: 'Niobium', Co: 'Cobalt', W: 'Tungsten', Ta: 'Tantalum', B: 'Boron', N: 'Nitrogen',Mg: 'Magnesium', Si: 'Silicon', Cu: 'Copper', Zn: 'Zinc', Mn: 'Manganese', Fe: 'Iron', Ti: 'Titanium', Zr: 'Zirconium', Li: 'Lithium', Sc: 'Scandium', Ni: 'Nickel', Cr: 'Chromium', H: 'Hydrogen', Hf: 'Hafnium', La: 'Lanthanum', O: 'Oxygen', P: 'Phosphorus', Pd: 'Palladium', S: 'Sulfur', V: 'Vanadium', Y: 'Yttrium'};
const properties = {
  yield: {name: 'Yield strength', unit: 'MPa', direction: 'max', note: 'Requires a calibrated strength model and material-condition data.'},
  density: {name: 'Density', unit: 'g/cm³', direction: 'min', note: 'Requires phase molar-volume or density data at the selected conditions.'},
  toughness: {name: 'Fracture toughness (K_IC)', unit: 'MPa·√m', direction: 'max', note: 'Requires suitable fracture data and a validated model for the alloy and condition.'},
  modulus: {name: "Young’s modulus", unit: 'GPa', direction: 'max', note: 'Requires elastic-property data and a supported phase averaging model.'},
};
// Representative standard atomic weights are used ONLY to order family tiles,
// never for composition conversion or scientific calculations. Interval elements
// use representative values. Source: https://www.ciaaw.org/atomic-weights.htm
const alloyBases = [
  ['Mg', 'Magnesium', 24.305], ['Al', 'Aluminum', 26.9815384],
  ['Ti', 'Titanium', 47.867], ['Fe', 'Iron', 55.845],
  ['Co', 'Cobalt', 58.933194], ['Ni', 'Nickel', 58.6934],
  ['Cu', 'Copper', 63.546], ['Zn', 'Zinc', 65.38],
  ['Zr', 'Zirconium', 91.222], ['Ag', 'Silver', 107.8682],
  ['W', 'Tungsten', 183.84], ['Pt', 'Platinum', 195.084],
  ['Au', 'Gold', 196.966570], ['Pb', 'Lead', 207.2],
].sort((a, b) => a[2] - b[2]);

function alloyFamilyGrid() {
  return alloyBases.map(([symbol, name]) => {
    const available = symbol in families;
    return `<button type="button" class="family-tile ${available ? 'family-available' : ''}" data-family="${symbol}" ${available ? `id="family-${symbol.toLowerCase()}" aria-pressed="false" aria-label="${name}-based alloys, setup preview available"` : `disabled aria-label="${name}-based alloys, not available yet"`}><span class="family-symbol" aria-hidden="true">${symbol}</span><span class="family-name">${name}</span></button>`;
  }).join('') + '<button type="button" class="family-tile family-other" data-family="other" disabled aria-label="Other alloy family, not available yet"><span class="family-symbol" aria-hidden="true">+</span><span class="family-name">Other</span></button>';
}

export function initOptimization(selectFamily, selectStep = () => {}) {
  const root = document.getElementById('optimization-root');
  let step = 0, family = null, nextRow = 0, mode = 'optimize';
  const activeSteps = () => mode === 'create' ? [0, 1, 2, 4] : [0, 1, 2, 3, 4];
  const ranges = new Map();
  let supportedElements = null;
  root.innerHTML = `
    <nav class="optimizer-steps" aria-label="Alloy optimization setup">${steps.map((name, i) => `<button type="button" data-opt-step="${i}" aria-label="${i + 1}. ${name}" ${i ? 'disabled' : ''}><span class="step-number">${i + 1}</span><span>${name}</span></button>`).join('')}</nav>
    <form id="optimizer-form" novalidate>
      <div class="optimizer-panel panel">
        <section data-opt-panel="0" aria-labelledby="opt-family-heading">
          <div class="opt-section-heading"><h2 id="opt-family-heading" tabindex="-1">Choose alloy family</h2></div>
          <div class="family-layout">
            <div class="alloy-family-grid" role="group" aria-label="Alloy base families, sorted by increasing atomic weight">${alloyFamilyGrid()}</div>
            <aside class="family-detail" aria-label="Selected alloy family"><h3>Select an alloy family</h3><p class="fine">MatCalc thermodynamic sources</p></aside>
          </div>
        </section>
        <section data-opt-panel="1" aria-labelledby="opt-composition-heading" hidden>
          <div class="opt-section-heading composition-header">
            <h2 id="opt-composition-heading" tabindex="-1">Select composition</h2>
            <fieldset class="opt-fieldset" aria-describedby="basis-help"><legend class="visually-hidden">Composition basis</legend><div class="basis-options"><label><input type="radio" name="opt-basis" value="mass" checked> Mass (wt%)</label><label><input type="radio" name="opt-basis" value="atomic"> Atomic (at%)</label></div><p class="fine" id="basis-help" hidden>Entered values are kept when switching basis.</p></fieldset>
          </div>
          <div class="composition-layout">
            <fieldset class="opt-fieldset"><legend>Alloying elements</legend><div class="addition-options">${Object.entries(additions).map(([symbol, name]) => `<label><input type="checkbox" value="${symbol}" name="opt-element"><strong>${symbol}</strong><span>${name}</span></label>`).join('')}</div><p class="fine" id="composition-source-help">Loading source elements…</p></fieldset>
            <section class="composition-editor" aria-labelledby="composition-title">
              <div class="composition-heading"><h3 id="composition-title">Composition bounds</h3><span id="composition-unit">wt%</span></div>
              <div class="balance-strip"><span id="balance-label">Base metal · balance</span><output id="alloy-balance">100 wt%</output></div>
              <div class="alloy-proportions" id="alloy-proportions" role="img" aria-label="Composition proportions" hidden></div>
              <p class="fine" id="composition-empty">Choose an alloying element.</p>
              <div id="composition-ranges"></div>
            </section>
          </div>
        </section>
        <section data-opt-panel="2" aria-labelledby="opt-condition-heading" hidden>
          <div class="opt-section-heading"><h2 id="opt-condition-heading" tabindex="-1">Processing</h2></div>
          ${processingMarkup}
        </section>
        <section data-opt-panel="3" aria-labelledby="opt-goals-heading" hidden>
          <div class="opt-section-heading"><h2 id="opt-goals-heading" tabindex="-1">What are you optimizing for?</h2></div>
          <div class="opt-rule-heading"><h3>Optimization goals</h3><button class="glass-button" type="button" id="add-opt-goal">+ Add goal</button></div><div id="opt-goals" class="opt-rules"></div>
          <div class="opt-rule-heading"><h3>Property limits</h3><button class="glass-button" type="button" id="add-opt-limit">+ Add limit</button></div><div id="opt-limits" class="opt-rules"></div><p class="fine" id="opt-no-limits">No property limits set.</p>
        </section>
        <section data-opt-panel="4" aria-labelledby="opt-review-heading" hidden>
          <div class="opt-section-heading"><h2 id="opt-review-heading" tabindex="-1">Review your alloy setup</h2></div>
          <div id="opt-review" class="opt-review"></div>
          <div class="opt-readiness"><h3>Simulate phases</h3><p class="fine" id="simulation-composition-help">Nominal additions are half their maximum, with the base metal as balance. Arc melting uses equilibrium cooling; property goals do not affect this calculation.</p><div class="phase-actions"><button class="primary" type="button" id="phase-run">Simulate phases</button><button class="glass-button" type="button" id="phase-cancel" hidden>Cancel calculation</button><button class="glass-button" type="button" id="phase-export" hidden>Export phase JSON</button></div><p id="phase-status" class="status fine" role="status" aria-live="polite"></p><progress id="phase-progress" max="1" hidden aria-label="Phase calculation progress"></progress><div id="phase-result" hidden></div><p class="fine" id="optimization-limitations">Strength prediction and alloy optimization are not connected.</p></div>
        </section>
      </div>
      <p class="status error" id="opt-error" role="alert" hidden></p>
      <div class="optimizer-actions"><button class="glass-button" id="opt-previous" type="button">Previous</button><button class="glass-button opt-next" id="opt-next" type="submit">Next <svg aria-hidden="true"><use href="#icon-arrow"/></svg></button></div>
    </form>`;

  const $ = id => document.getElementById(id);
  const panels = [...root.querySelectorAll('[data-opt-panel]')];
  const tabs = [...root.querySelectorAll('[data-opt-step]')];
  const basis = () => root.querySelector('[name="opt-basis"]:checked').value;
  const unit = () => basis() === 'mass' ? 'wt%' : 'at%';
  const error = message => { $('opt-error').textContent = message; $('opt-error').hidden = !message; };
  const escape = value => String(value).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const number = value => Number(value).toLocaleString(undefined, {maximumSignificantDigits: 12});
  const exactBase = () => 100 - [...ranges.values()].reduce((sum, range) => sum + range.amount.valueAsNumber, 0);
  const balanceError = () => `Keep the combined additions below 100 ${unit()} to leave a positive ${family || 'base metal'} balance.`;

  function showStep(index, focus = true) {
    step = index; error('');
    document.body.dataset.optimizerStep = String(index);
    selectStep(index);
    panels.forEach((panel, i) => { panel.hidden = i !== index; });
    syncNavigation();
    $('opt-previous').hidden = index === 0; $('opt-next').hidden = index === 4;
    if (index === 2) processing.redraw();
    if (index === 4) renderReview();
    if (focus) {
      const panel = panels[index];
      panel.classList.remove('opt-step-enter'); void panel.offsetWidth; panel.classList.add('opt-step-enter');
      panel.querySelector('h2').focus({preventScroll: true});
      window.scrollTo({top: 0, behavior: 'instant'});
    }
  }

  function updateBalance() {
    let low = 0, high = 0;
    ranges.forEach(range => { low += Number(range.min.value); high += Number(range.max.value); });
    $('composition-unit').textContent = unit();
    const create = mode === 'create', base = exactBase();
    const valid = [...ranges.values()].every(range => range.amount.checkValidity());
    const showProportions = create && family && valid && base > 0;
    $('alloy-balance').textContent = create
      ? (showProportions ? `${number(base)} ${unit()}` : '—')
      : `${number(100 - high)}–${number(100 - low)} ${unit()}`;
    $('alloy-balance').classList.toggle('invalid-balance', create ? valid && base <= 0 : high >= 100);
    const bar = $('alloy-proportions');
    bar.hidden = !showProportions;
    if (showProportions) {
      const parts = [[family, base], ...[...ranges].map(([symbol, range]) => [symbol, range.amount.valueAsNumber])];
      const segments = parts.map(([symbol, amount], index) => {
        const segment = document.createElement('span');
        segment.style.flexBasis = `${amount}%`;
        const hue = (index - 1) * 137.508 + 27;
        segment.style.setProperty('--element-hue', hue);
        ranges.get(symbol)?.row.style.setProperty('--element-hue', hue);
        segment.title = `${symbol} ${number(amount)} ${unit()}`;
        return segment;
      });
      bar.replaceChildren(...segments);
      bar.setAttribute('aria-label', segments.map(segment => segment.title).join(', '));
    }
    ranges.forEach((range, symbol) => {
      range.min.setAttribute('aria-label', `${symbol} minimum (${unit()})`);
      range.max.setAttribute('aria-label', `${symbol} maximum (${unit()})`);
      range.amount.setAttribute('aria-label', `${symbol} amount (${unit()})`);
    });
  }

  function syncElements() {
    const selected = [...root.querySelectorAll('[name="opt-element"]:checked')].map(input => input.value);
    for (const [symbol, range] of ranges) if (!selected.includes(symbol)) { range.row.remove(); ranges.delete(symbol); }
    selected.forEach(symbol => {
      if (ranges.has(symbol)) return;
      const row = document.createElement('div'); row.className = 'composition-row';
      const ironCarbon = family === 'Fe' && symbol === 'C';
      const amount = ironCarbon ? (basis() === 'mass' ? 0.4 : 1.8) : 5;
      const maximum = ironCarbon ? 2 * amount : amount;
      row.innerHTML = `<span class="element-token">${symbol}</span><span class="element-name">${additions[symbol]}</span><div class="composition-bound"><label for="opt-${symbol}-min">Minimum</label><input id="opt-${symbol}-min" type="number" min="0" max="100" step="any" value="0" required></div><div class="composition-bound"><label for="opt-${symbol}-max">Maximum</label><input id="opt-${symbol}-max" type="number" min="0" max="100" step="any" value="${maximum}" required></div><div class="composition-amount"><label for="opt-${symbol}-amount">Amount</label><input id="opt-${symbol}-amount" type="number" min="0.000001" max="99.999999" step="any" value="${amount}" required></div>`;
      $('composition-ranges').append(row);
      ranges.set(symbol, {row, min: row.querySelectorAll('input')[0], max: row.querySelectorAll('input')[1], amount: row.querySelectorAll('input')[2]});
    });
    $('composition-empty').hidden = selected.length > 0;
    processing.setAdditions(selected);
    syncCompositionMode();
  }

  function syncCompositionMode() {
    const create = mode === 'create';
    ranges.forEach(range => {
      range.row.classList.toggle('composition-exact', create);
      range.row.querySelectorAll('.composition-bound').forEach(item => { item.hidden = create; });
      range.row.querySelector('.composition-amount').hidden = !create;
      range.min.disabled = range.max.disabled = create;
      range.amount.disabled = !create;
    });
    updateBalance();
  }

  function filterElements(elements) {
    supportedElements = elements;
    const allowed = new Set(elements || []), removed = [];
    for (const element of allowed) {
      if (!/^[A-Z]{1,2}$/.test(element)) continue;
      const symbol = element[0] + element.slice(1).toLowerCase();
      if (root.querySelector(`[name="opt-element"][value="${symbol}"]`)) continue;
      additions[symbol] ??= symbol;
      const label = document.createElement('label');
      label.innerHTML = `<input type="checkbox" value="${symbol}" name="opt-element"><strong>${symbol}</strong><span>${additions[symbol]}</span>`;
      label.querySelector('input').addEventListener('change', syncElements);
      root.querySelector('.addition-options').append(label);
    }
    root.querySelectorAll('[name="opt-element"]').forEach(input => {
      const supported = allowed.has(input.value.toUpperCase()) && input.value !== family;
      input.disabled = !supported;
      input.closest('label').hidden = !supported;
      if (!supported && elements && input.checked) { removed.push(input.value); input.checked = false; }
    });
    $('composition-source-help').textContent = elements ? `${removed.length ? `Removed unsupported additions: ${removed.join(', ')}. ` : ''}Elements declared by the selected source; interaction coverage remains unverified.` : 'Loading source elements…';
    if (elements) { syncElements(); syncNavigation(); }
  }

  function addRule(kind, property = 'yield', focus = false) {
    const id = ++nextRow, goal = kind === 'goal';
    const row = document.createElement('div'); row.className = 'opt-rule'; row.dataset.kind = kind;
    row.innerHTML = `<div><label for="rule-property-${id}">${goal ? 'Goal' : 'Limit'} property</label><select id="rule-property-${id}" class="rule-property">${Object.entries(properties).map(([key, p]) => `<option value="${key}">${p.name}</option>`).join('')}</select></div><div><label for="rule-direction-${id}">${goal ? 'Direction' : 'Requirement'}</label><select id="rule-direction-${id}" class="rule-direction">${goal ? '<option value="max">Maximize</option><option value="min">Minimize</option>' : '<option value="max">At most (≤)</option><option value="min">At least (≥)</option>'}</select></div>${goal ? '' : `<div><label for="rule-value-${id}" class="rule-unit">Value</label><input id="rule-value-${id}" class="rule-value" type="number" min="0.000001" step="any" required></div>`}<button class="opt-remove" type="button" aria-label="Remove ${goal ? 'goal' : 'limit'}">×</button><p class="fine rule-coverage"></p>`;
    row.querySelector('.rule-property').value = property;
    const update = () => {
      const p = properties[row.querySelector('.rule-property').value];
      row.querySelector('.rule-coverage').textContent = `Model/data needed · ${p.note}`;
      row.querySelector('.opt-remove').setAttribute('aria-label', `Remove ${p.name} ${kind}`);
      if (goal) row.querySelector('.rule-direction').value = p.direction;
      else row.querySelector('.rule-unit').textContent = `Value (${p.unit})`;
    };
    row.querySelector('.rule-property').addEventListener('change', update);
    row.querySelector('.opt-remove').addEventListener('click', () => {
      row.remove(); $('opt-no-limits').hidden = !!$('opt-limits').children.length;
      syncNavigation(); $(goal ? 'add-opt-goal' : 'add-opt-limit').focus();
    });
    $(goal ? 'opt-goals' : 'opt-limits').append(row); update();
    $('opt-no-limits').hidden = !!$('opt-limits').children.length;
    if (focus) { syncNavigation(); row.querySelector('select').focus(); }
  }

  function validationIssue(index) {
    for (const field of panels[index].querySelectorAll('input, select, textarea')) {
      if (!field.disabled && !field.checkValidity()) return {message: field.validationMessage, field};
    }
    if (index === 0 && !family) return {message: 'Select an alloy family to continue.', field: $('family-al')};
    if (index === 1) {
      if (!supportedElements) return {message: 'Wait for the source element list to load.'};
      if (!ranges.size) return {message: 'Choose at least one alloying element.'};
      if (ranges.size > 8) return {message: 'Phase simulation supports up to eight alloying additions.'};
      if (mode === 'create') {
        if (exactBase() <= 0) return {message: balanceError(), field: [...ranges.values()].at(-1).amount};
        return null;
      }
      let high = 0;
      for (const [symbol, range] of ranges) {
        if (Number(range.min.value) > Number(range.max.value)) return {message: `${symbol}: minimum must not exceed maximum.`, field: range.min};
        high += Number(range.max.value);
      }
      if (high >= 100) return {message: `Keep the combined maximum additions below 100% so ${families[family].name.toLowerCase()} remains in the balance.`};
    }
    if (index === 2 && Number($('process-melt-temperature').value) + 273.15 <= Math.max(Number($('process-start-temperature').value) + 273.15, Number($('opt-temperature').value))) return {message: 'The melt temperature must exceed the initial and final temperatures.', field: $('process-melt-temperature')};
    if (index === 3 && mode === 'optimize') {
      if (!$('opt-goals').children.length) return {message: 'Add at least one optimization goal.', field: $('add-opt-goal')};
      const goals = [...$('opt-goals').children].map(row => row.querySelector('.rule-property').value);
      if (new Set(goals).size !== goals.length) return {message: 'Use one goal per property.'};
      const bounds = {};
      for (const row of $('opt-limits').children) {
        const property = row.querySelector('.rule-property').value;
        const dir = row.querySelector('.rule-direction').value, value = Number(row.querySelector('.rule-value').value);
        bounds[property] ??= {min: -Infinity, max: Infinity};
        bounds[property][dir] = dir === 'min' ? Math.max(bounds[property][dir], value) : Math.min(bounds[property][dir], value);
        if (bounds[property].min > bounds[property].max) return {message: `${properties[property].name}: lower limit exceeds upper limit.`};
      }
    }
    return null;
  }
  function syncNavigation() {
    error('');
    const active = activeSteps();
    let reachable = 0;
    while (reachable < active.length - 1 && !validationIssue(active[reachable])) reachable++;
    tabs.forEach((tab, i) => {
      const position = active.indexOf(i);
      tab.hidden = position < 0;
      tab.disabled = position < 0 || (position > reachable && i !== step);
      if (position >= 0) {
        tab.querySelector('.step-number').textContent = position + 1;
        tab.setAttribute('aria-label', `${position + 1}. ${steps[i]}`);
      }
      if (i === step) tab.setAttribute('aria-current', 'step'); else tab.removeAttribute('aria-current');
      tab.classList.toggle('step-complete', position >= 0 && position < reachable);
    });
    const issue = validationIssue(step);
    $('opt-next').disabled = active.indexOf(step) > reachable || !!issue;
    if (issue && ((issue.field?.validity?.valid) || (!issue.field && !(step === 1 && !ranges.size)))) error(issue.message);
  }
  function validate() {
    const issue = validationIssue(step);
    if (!issue) { error(''); return true; }
    error(issue.message);
    issue.field?.focus();
    if (issue.field?.reportValidity) issue.field.reportValidity();
    return false;
  }

  function renderReview() {
    const card = (title, content, index) => `<article class="review-card"><div><h3>${title}</h3><button class="text-button" type="button" data-review-edit="${index}" aria-label="Edit ${title}">Edit</button></div>${content}</article>`;
    const rules = kind => [...$(kind === 'goal' ? 'opt-goals' : 'opt-limits').children].map(row => {
      const p = properties[row.querySelector('.rule-property').value], direction = row.querySelector('.rule-direction').value;
      return `<li>${escape(p.name)} <strong>${kind === 'goal' ? (direction === 'max' ? '↑ Maximize' : '↓ Minimize') : `${direction === 'max' ? '≤' : '≥'} ${number(row.querySelector('.rule-value').value)} ${p.unit}`}</strong></li>`;
    }).join('');
    const process = processing.summary();
    const nominal = [...ranges].map(([symbol, range]) => `${symbol} ${number(Number(range.max.value) * .5)} ${unit()}`);
    const baseNominal = 100 - [...ranges.values()].reduce((sum, range) => sum + Number(range.max.value) * .5, 0);
    $('opt-review').innerHTML =
      card('Alloy family', `<p>${families[family].name}-based alloys</p><p class="fine">${escape($('process-source').selectedOptions[0].textContent)} · coverage unverified</p>`, 0) +
      card('Composition', `<p class="fine">${basis() === 'mass' ? 'Mass' : 'Atomic'} percent · ${unit()}</p><ul>${[...ranges].map(([symbol, range]) => `<li>${symbol}<strong>${mode === 'create' ? number(range.amount.value) : `${number(range.min.value)}–${number(range.max.value)}`} ${unit()}</strong></li>`).join('')}<li>${family} · balance<strong>${escape($('alloy-balance').textContent)}</strong></li></ul>${mode === 'create' ? '<p class="fine">Simulation uses these exact amounts.</p>' : `<p class="fine">Simulation nominal: ${nominal.join(' · ')} · ${family} ${number(baseNominal)} ${unit()}. Minima do not constrain the half-maximum rule.</p>`}`, 1) +
      card('Processing', `<p>${escape(process.route)}</p><ul>${process.phaseSelection ? `<li>Phase selection<strong>${escape(process.phaseSelection)}</strong></li>` : ''}<li>Initial annealed state<strong>${number(process.start)} °C</strong></li><li>Fully mixed melt<strong>${number(process.melt)} °C</strong></li><li>Final temperature<strong>${number(process.end)} K</strong></li><li>Pressure<strong>${number($('opt-pressure').value)} Pa</strong></li></ul>${$('opt-condition-notes').value ? `<p class="fine review-notes">${escape($('opt-condition-notes').value)}</p>` : ''}`, 2) +
      (mode === 'create' ? '' : card('Goals & limits', `<ul>${rules('goal')}</ul><h4>Property limits</h4>${$('opt-limits').children.length ? `<ul>${rules('limit')}</ul>` : '<p class="fine">None set</p>'}<p class="fine">All selected properties need models/data.</p>`, 3));
    root.querySelectorAll('[data-review-edit]').forEach(button => button.addEventListener('click', () => showStep(Number(button.dataset.reviewEdit))));
  }

  root.querySelectorAll('.family-available').forEach(button => button.addEventListener('click', () => {
    family = button.dataset.family;
    processing.setFamily(family);
    root.querySelectorAll('.family-available').forEach(tile => tile.setAttribute('aria-pressed', String(tile === button)));
    root.querySelector('.family-detail h3').textContent = `${families[family].name}-based alloys`;
    root.querySelector('.family-detail p').textContent = families[family].source;
    $('balance-label').innerHTML = `<strong>${family}</strong> ${families[family].name} · balance`;
    syncElements();
    error(''); selectFamily(family); syncNavigation();
    phaseSimulation.changed();
  }));
  root.querySelectorAll('[name="opt-element"]').forEach(input => input.addEventListener('change', syncElements));
  root.querySelectorAll('[name="opt-basis"]').forEach(input => input.addEventListener('change', () => {
    $('basis-help').hidden = false;
    updateBalance();
  }));
  $('composition-ranges').addEventListener('input', updateBalance);
  // Clear stale feedback when the user edits; Next revalidates the entire step.
  root.addEventListener('input', () => { error(''); syncNavigation(); });
  root.addEventListener('change', () => { error(''); syncNavigation(); });
  $('add-opt-goal').addEventListener('click', () => addRule('goal', 'density', true));
  $('add-opt-limit').addEventListener('click', () => addRule('limit', 'density', true));
  const nextStep = () => activeSteps()[activeSteps().indexOf(step) + 1];
  const previousStep = () => activeSteps()[activeSteps().indexOf(step) - 1];
  $('opt-previous').addEventListener('click', () => showStep(previousStep()));
  $('optimizer-form').addEventListener('submit', event => { event.preventDefault(); if (step < 4 && validate()) showStep(nextStep()); });
  tabs.forEach((tab, i) => tab.addEventListener('click', () => {
    // Forward jumps validate intervening screens, including edits made after review.
    if (!activeSteps().includes(i)) return;
    if (i > step) { while (step < i) { if (!validate()) return; showStep(nextStep(), false); } }
    showStep(i);
  }));
  const processing = initProcessing(root, () => { error(''); syncNavigation(); phaseSimulation.changed(); }, elements => filterElements(elements));
  const phaseSimulation = initPhaseSimulation(root, () => ({family: family?.toUpperCase(),
    database_id: $('process-source').value || null, composition_basis: basis(), composition_mode: mode === 'create' ? 'fixed' : 'bounds',
    additions: [...ranges].map(([element, range]) => ({element: element.toUpperCase(), minimum: Number(mode === 'create' ? range.amount.value : range.min.value), maximum: Number(mode === 'create' ? range.amount.value : range.max.value)})),
    route: 'arc_melting', cooling_model: 'equilibrium', phase_policy: processing.phasePolicy(),
    initial_temperature_k: Number($('process-start-temperature').value) + 273.15,
    melt_temperature_k: Number($('process-melt-temperature').value) + 273.15,
    final_temperature_k: Number($('opt-temperature').value), pressure_pa: Number($('opt-pressure').value), cooling_points: 21,
    notes: $('opt-condition-notes').value,
    include_reference_properties: $('process-reference-properties').checked,
    allow_screening_estimates: $('process-screening-properties').checked,
    use_physical_density: $('process-physical-density').checked,
  }), () => {
    for (let index = 0; index <= 2; index++) {
      const issue = validationIssue(index);
      if (issue) { showStep(index); error(issue.message); issue.field?.focus(); return false; }
    }
    return true;
  });
  addRule('goal'); showStep(0, false);
  return {
    get mode() { return mode; },
    setMode(value) {
      mode = value === 'create' ? 'create' : 'optimize';
      const create = mode === 'create';
      root.dataset.alloyMode = mode;
      $('optimize-heading').textContent = create ? 'Create alloy' : 'Optimize alloy';
      root.querySelector('.optimizer-steps').setAttribute('aria-label', create ? 'Create alloy setup' : 'Alloy optimization setup');
      root.querySelector('.optimizer-steps').style.setProperty('--step-count', activeSteps().length);
      $('composition-title').textContent = create ? 'Composition amounts' : 'Composition bounds';
      $('simulation-composition-help').textContent = create ? 'Simulation uses your exact composition. Arc melting uses equilibrium cooling.' : 'Nominal additions are half their maximum, with the base metal as balance. Arc melting uses equilibrium cooling; property goals do not affect this calculation.';
      $('optimization-limitations').hidden = create;
      syncCompositionMode(); showStep(0, false); phaseSimulation.changed();
    },
    previousStep() { if (step === 0) return false; showStep(previousStep()); return true; },
  };
}
