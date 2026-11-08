import {processingMarkup, initProcessing} from './processing.js';
// UI-only setup. No scientific coverage or property predictions are inferred
// from these choices. A future backend must validate every model and source.
const steps = ['Alloy family', 'Composition', 'Processing', 'Goals & limits', 'Review'];
const additions = {Mg: 'Magnesium', Si: 'Silicon', Cu: 'Copper', Zn: 'Zinc', Mn: 'Manganese', Fe: 'Iron', Ti: 'Titanium', Zr: 'Zirconium', Li: 'Lithium', Sc: 'Scandium', Ni: 'Nickel', Cr: 'Chromium'};
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
    const al = symbol === 'Al';
    return `<button type="button" class="family-tile ${al ? 'family-available' : ''}" data-family="${symbol}" ${al ? 'id="family-al" aria-pressed="false" aria-label="Aluminum-based alloys, setup preview available"' : `disabled aria-label="${name}-based alloys, not available yet"`}><span class="family-symbol" aria-hidden="true">${symbol}</span><span class="family-name">${name}</span></button>`;
  }).join('') + '<button type="button" class="family-tile family-other" data-family="other" disabled aria-label="Other alloy family, not available yet"><span class="family-symbol" aria-hidden="true">+</span><span class="family-name">Other</span></button>';
}

export function initOptimization(selectFamily) {
  const root = document.getElementById('optimization-root');
  let step = 0, family = false, nextRow = 0;
  const ranges = new Map();
  root.innerHTML = `
    <div class="optimizer-intro"><span class="optimizer-badge">Setup preview</span></div>
    <nav class="optimizer-steps" aria-label="Alloy optimization setup">${steps.map((name, i) => `<button type="button" data-opt-step="${i}" aria-label="${i + 1}. ${name}" ${i ? 'disabled' : ''}><span class="step-number">${i + 1}</span><span>${name}</span></button>`).join('')}</nav>
    <p class="optimizer-progress fine" id="optimizer-progress" aria-live="polite"></p>
    <form id="optimizer-form" novalidate>
      <div class="optimizer-panel panel">
        <section data-opt-panel="0" aria-labelledby="opt-family-heading">
          <div class="opt-section-heading"><h2 id="opt-family-heading" tabindex="-1">Choose your alloy family</h2></div>
          <div class="family-layout">
            <div class="alloy-family-grid" role="group" aria-label="Alloy base families, sorted by increasing atomic weight">${alloyFamilyGrid()}</div>
            <aside class="family-detail" aria-label="Selected alloy family"><h3>Aluminum-based alloys</h3><p class="fine">COST 507 · planned</p></aside>
          </div>
        </section>
        <section data-opt-panel="1" aria-labelledby="opt-composition-heading" hidden>
          <div class="opt-section-heading"><h2 id="opt-composition-heading" tabindex="-1">What goes into your alloy?</h2></div>
          <fieldset class="opt-fieldset"><legend>Composition basis</legend><div class="basis-options"><label><input type="radio" name="opt-basis" value="mass" checked> Mass percent (wt%)</label><label><input type="radio" name="opt-basis" value="atomic"> Atomic percent (at%)</label></div><p class="fine" id="basis-help">Changing basis keeps the entered numbers; it does not convert them.</p></fieldset>
          <fieldset class="opt-fieldset"><legend>Alloying elements</legend><div class="addition-options">${Object.entries(additions).map(([symbol, name]) => `<label><input type="checkbox" value="${symbol}" name="opt-element"><strong>${symbol}</strong><span>${name}</span></label>`).join('')}</div></fieldset>
          <div class="composition-heading"><h3>Composition bounds</h3><span class="fine" id="composition-unit">wt%</span></div>
          <p class="fine" id="composition-empty">Select at least one alloying element above.</p>
          <div id="composition-ranges"></div>
          <div class="balance-strip"><span><strong>Al</strong> Aluminum · balance</span><output id="al-balance">100 wt%</output></div>
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
          <div class="opt-readiness"><h3>Calculation is not connected yet</h3><p class="fine">Your search is ready to review. Running it will require compatible database coverage and validated property models for the chosen alloy and condition.</p><button class="primary" type="button" disabled aria-describedby="opt-run-help">Run optimization · coming later</button><p class="fine" id="opt-run-help">No property predictions or optimized candidates are produced by this preview.</p></div>
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

  function showStep(index, focus = true) {
    step = index; error('');
    document.body.dataset.optimizerStep = String(index);
    panels.forEach((panel, i) => { panel.hidden = i !== index; });
    syncNavigation();
    $('optimizer-progress').textContent = `Step ${index + 1} of ${steps.length} · ${steps[index]}`;
    $('opt-previous').hidden = index === 0; $('opt-next').hidden = index === steps.length - 1;
    if (index === 2) processing.redraw();
    if (index === 4) renderReview();
    if (focus) {
      const panel = panels[index];
      panel.classList.remove('opt-step-enter'); void panel.offsetWidth; panel.classList.add('opt-step-enter');
      panel.querySelector('h2').focus({preventScroll: true});
      $('optimizer-progress').scrollIntoView({block: 'start', behavior: 'instant'});
    }
  }

  function updateBalance() {
    let low = 0, high = 0;
    ranges.forEach(range => { low += Number(range.min.value); high += Number(range.max.value); });
    $('composition-unit').textContent = unit();
    $('al-balance').textContent = `${number(100 - high)}–${number(100 - low)} ${unit()}`;
    $('al-balance').classList.toggle('invalid-balance', high >= 100);
    ranges.forEach((range, symbol) => {
      range.min.setAttribute('aria-label', `${symbol} minimum (${unit()})`);
      range.max.setAttribute('aria-label', `${symbol} maximum (${unit()})`);
    });
  }

  function syncElements() {
    const selected = [...root.querySelectorAll('[name="opt-element"]:checked')].map(input => input.value);
    for (const [symbol, range] of ranges) if (!selected.includes(symbol)) { range.row.remove(); ranges.delete(symbol); }
    selected.forEach(symbol => {
      if (ranges.has(symbol)) return;
      const row = document.createElement('div'); row.className = 'composition-row';
      row.innerHTML = `<span class="element-token">${symbol}</span><span class="element-name">${additions[symbol]}</span><div><label for="opt-${symbol}-min">Minimum</label><input id="opt-${symbol}-min" type="number" min="0" max="100" step="any" value="0" required></div><div><label for="opt-${symbol}-max">Maximum</label><input id="opt-${symbol}-max" type="number" min="0" max="100" step="any" value="5" required></div>`;
      $('composition-ranges').append(row);
      ranges.set(symbol, {row, min: row.querySelectorAll('input')[0], max: row.querySelectorAll('input')[1]});
    });
    $('composition-empty').hidden = selected.length > 0;
    updateBalance();
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
    if (index === 0 && !family) return {message: 'Select the aluminum family to continue.', field: $('family-al')};
    if (index === 1) {
      if (!ranges.size) return {message: 'Choose at least one alloying element.'};
      let high = 0;
      for (const [symbol, range] of ranges) {
        if (Number(range.min.value) > Number(range.max.value)) return {message: `${symbol}: minimum must not exceed maximum.`, field: range.min};
        high += Number(range.max.value);
      }
      if (high >= 100) return {message: 'Keep the combined maximum additions below 100% so aluminum remains in the balance.'};
    }
    if (index === 2) {
      let previous = Number($('process-start-temperature').value);
      for (const item of processing.readSchedule()) {
        if (item.type === 'quench' && item.target >= previous) return {message: 'A quench target must be below the preceding temperature.'};
        previous = item.target;
      }
    }
    if (index === 3) {
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
    let reachable = 0;
    while (reachable < 4 && !validationIssue(reachable)) reachable++;
    tabs.forEach((tab, i) => {
      tab.disabled = i > reachable && i !== step;
      if (i === step) tab.setAttribute('aria-current', 'step'); else tab.removeAttribute('aria-current');
      tab.classList.toggle('step-complete', i < reachable);
    });
    const issue = validationIssue(step);
    $('opt-next').disabled = step > reachable || !!issue;
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
    $('opt-review').innerHTML =
      card('Alloy family', '<p>Aluminum-based alloys</p><p class="fine">COST 507 · planned source, coverage unverified</p>', 0) +
      card('Composition', `<p class="fine">${basis() === 'mass' ? 'Mass' : 'Atomic'} percent · ${unit()}</p><ul>${[...ranges].map(([symbol, range]) => `<li>${symbol}<strong>${number(range.min.value)}–${number(range.max.value)} ${unit()}</strong></li>`).join('')}<li>Al · balance<strong>${escape($('al-balance').textContent)}</strong></li></ul>`, 1) +
      card('Processing', `<p>${escape(process.route)}</p><ul><li>Starting temperature<strong>${number(process.start)} °C</strong></li>${process.events.map((item, i) => `<li>${i + 1}. ${item.label}<strong>${number(item.target)} °C · ${number(item.ramp)} min ramp${item.hold ? ` · ${number(item.hold)} min hold` : ''}</strong></li>`).join('')}<li>Final work hardening<strong>${escape(process.work)}</strong></li><li>Evaluation temperature<strong>${number($('opt-temperature').value)} K</strong></li><li>Pressure<strong>${number($('opt-pressure').value)} Pa</strong></li></ul>${$('opt-condition-notes').value ? `<p class="fine review-notes">${escape($('opt-condition-notes').value)}</p>` : ''}`, 2) +
      card('Goals & limits', `<ul>${rules('goal')}</ul><h4>Property limits</h4>${$('opt-limits').children.length ? `<ul>${rules('limit')}</ul>` : '<p class="fine">None set</p>'}<p class="fine">All selected properties need models/data.</p>`, 3);
    root.querySelectorAll('[data-review-edit]').forEach(button => button.addEventListener('click', () => showStep(Number(button.dataset.reviewEdit))));
  }

  $('family-al').addEventListener('click', () => {
    family = true; $('family-al').setAttribute('aria-pressed', 'true');
    error(''); selectFamily('Al'); syncNavigation();
  });
  root.querySelectorAll('[name="opt-element"]').forEach(input => input.addEventListener('change', syncElements));
  root.querySelectorAll('[name="opt-basis"]').forEach(input => input.addEventListener('change', updateBalance));
  $('composition-ranges').addEventListener('input', updateBalance);
  // Clear stale feedback when the user edits; Next revalidates the entire step.
  root.addEventListener('input', () => { error(''); syncNavigation(); });
  root.addEventListener('change', () => { error(''); syncNavigation(); });
  $('add-opt-goal').addEventListener('click', () => addRule('goal', 'density', true));
  $('add-opt-limit').addEventListener('click', () => addRule('limit', 'density', true));
  $('opt-previous').addEventListener('click', () => showStep(step - 1));
  $('optimizer-form').addEventListener('submit', event => { event.preventDefault(); if (step < 4 && validate()) showStep(step + 1); });
  tabs.forEach((tab, i) => tab.addEventListener('click', () => {
    // Forward jumps validate intervening screens, including edits made after review.
    if (i > step) { while (step < i) { if (!validate()) return; showStep(step + 1, false); } }
    showStep(i);
  }));
  const processing = initProcessing(root, () => { error(''); syncNavigation(); });
  addRule('goal'); showStep(0, false);
  return {previousStep() { if (step === 0) return false; showStep(step - 1); return true; }};
}
