const $ = id => document.getElementById(id);
const names = {AL: 'Aluminum', FE: 'Iron / steel'};
const number = value => value.toLocaleString(undefined, {maximumFractionDigits: 2});
const mpa = value => `${Math.round(value).toLocaleString()} MPa`;
const symbol = element => element[0] + element.slice(1).toLowerCase();

export function initStrength(api) {
  const mode = $('mechanical-mode'), form = $('strength-form'), family = $('strength-family');
  const condition = $('strength-condition'), additions = $('strength-additions'), add = $('strength-add');
  const run = $('strength-run'), output = $('strength-result'), status = $('strength-status');
  let families = new Map(), pending, busy = false, result, nextRow = 0;

  function message(text, error = false) {
    status.textContent = text;
    status.classList.toggle('error', error);
  }

  function refreshRows() {
    const rows = [...additions.children];
    const selected = rows.map(row => row.querySelector('select').value).filter(Boolean);
    const choices = families.get(family.value)?.elements || [];
    for (const row of rows) {
      const select = row.querySelector('select');
      for (const option of select.options) {
        option.disabled = option.value !== select.value && selected.includes(option.value);
      }
      row.querySelector('button').disabled = busy || rows.length === 1;
    }
    const total = rows.reduce((sum, row) => sum + (Number(row.querySelector('input').value) || 0), 0);
    $('strength-balance').textContent = family.value ? `${symbol(family.value)} balance · ${number(100 - total)} wt%` : '';
    add.disabled = busy || !choices.length || rows.length >= choices.length;
    run.disabled = busy || !families.has(family.value);
  }

  function addRow(focus = false) {
    const row = document.createElement('div'), select = document.createElement('select');
    const input = document.createElement('input'), remove = document.createElement('button');
    const index = ++nextRow;
    row.className = 'strength-row';
    select.setAttribute('aria-label', `Element ${index}`);
    select.required = true;
    select.append(new Option('Element', ''), ...families.get(family.value).elements.map(value => new Option(symbol(value), value)));
    input.setAttribute('aria-label', `Element ${index} amount (wt%)`);
    input.type = 'number';
    input.step = 'any';
    input.min = '0.000001';
    input.max = '50';
    input.placeholder = 'wt%';
    input.required = true;
    remove.type = 'button';
    remove.className = 'small-button';
    remove.setAttribute('aria-label', `Remove element ${index}`);
    remove.textContent = '×';
    remove.addEventListener('click', () => {
      row.remove();
      refreshRows();
      add.focus();
    });
    row.append(select, input, remove);
    additions.append(row);
    refreshRows();
    if (focus) select.focus();
  }

  function updateFamily() {
    const source = families.get(family.value);
    condition.replaceChildren(...Object.entries(source?.conditions || {}).map(([key, label]) => new Option(label, key)));
    condition.disabled = !source;
    additions.replaceChildren();
    nextRow = 0;
    if (source) addRow();
    refreshRows();
  }

  async function load() {
    if (pending || families.size) return;
    pending = api('/api/mechanical/strength/sources');
    try {
      const data = await pending;
      families = new Map(data.families.map(value => [value.id, value]));
      family.replaceChildren(...data.families.map(value => new Option(names[value.id], value.id)));
      updateFamily();
      message(families.size ? '' : 'Strength screening needs the local aluminum or steel reference table.');
    } catch (error) {
      message(error.message, true);
    } finally {
      pending = null;
    }
  }

  function render(value) {
    const {validation, strength_mpa: strength} = value;
    const chemistry = Object.entries(value.composition_wt_pct)
      .map(([element, amount]) => `${symbol(element)} ${amount.toLocaleString(undefined, {maximumFractionDigits: 6})}`)
      .join(', ');
    $('strength-heading').textContent = strength ? 'Strength estimates' : 'Outside data coverage';
    $('strength-summary').textContent = `${value.condition} · ${chemistry} wt%`;
    $('strength-metrics').replaceChildren(...(strength ? [['yield', 'Yield strength'], ['uts', 'Ultimate tensile strength']].map(([key, label]) => {
      const card = document.createElement('div'), term = document.createElement('dt'), desc = document.createElement('dd');
      const note = document.createElement('small');
      term.textContent = label;
      desc.textContent = mpa(strength[key]);
      note.textContent = `90th-percentile held-out error · ${mpa(validation.p90_absolute_error_mpa[key])}`;
      desc.append(note);
      card.append(term, desc);
      return card;
    }) : []));
    $('strength-validation').textContent = [
      ...value.warnings,
      `Held-out validation covered ${validation.covered_compositions} of ${validation.compositions} distinct compositions. Mean absolute error ${mpa(validation.mae_mpa.yield)} for yield and ${mpa(validation.mae_mpa.uts)} for UTS.`
    ].join(' ');
    $('strength-neighbors').replaceChildren(...value.neighbors.map(neighbor => {
      const row = document.createElement('li');
      const chem = Object.entries(neighbor.composition_wt_pct).filter(([element]) => element !== value.family)
        .map(([element, amount]) => `${symbol(element)} ${number(amount)}`).join(', ');
      row.textContent = `${chem || symbol(value.family)} wt% · yield ${number(neighbor.yield_mpa)} MPa · UTS ${number(neighbor.uts_mpa)} MPa`;
      return row;
    }));
    const link = document.createElement('a');
    link.href = value.provenance.source_url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = 'Source dataset';
    const details = value.assumptions.map(note => {
      const p = document.createElement('p');
      p.className = 'fine';
      p.textContent = note;
      return p;
    });
    $('strength-provenance').replaceChildren(link, ...details);
    output.hidden = false;
    if (!output.closest('.screen').hidden && mode.value === 'strength') {
      $('strength-heading').focus({preventScroll: true});
      if (matchMedia('(max-width: 850px)').matches) output.scrollIntoView({block: 'start'});
    }
  }

  mode.addEventListener('change', () => {
    $('strength-layout').hidden = mode.value !== 'strength';
    $('trace-layout').hidden = mode.value !== 'trace';
  });
  family.addEventListener('change', updateFamily);
  additions.addEventListener('input', refreshRows);
  add.addEventListener('click', () => addRow(true));
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || !families.has(family.value)) return;
    const composition = Object.fromEntries([...additions.children].map(row =>
      [row.querySelector('select').value, Number(row.querySelector('input').value)]));
    if (Object.keys(composition).length !== additions.children.length) {
      message('Choose different elements for each addition.', true);
      return;
    }
    busy = true;
    for (const control of form.elements) control.disabled = true;
    output.hidden = true;
    message('Estimating strength…');
    try {
      result = await api('/api/mechanical/strength', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({family: family.value, condition: condition.value, additions_wt_pct: composition})});
      render(result);
      message('');
    } catch (error) {
      message(error.message, true);
    } finally {
      busy = false;
      for (const control of form.elements) control.disabled = false;
      refreshRows();
    }
  });
  $('strength-export').addEventListener('click', () => {
    if (!result) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], {type: 'application/json'}));
    const link = document.createElement('a');
    link.href = url;
    link.download = `rutile-strength-${result.family}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  refreshRows();
  return load;
}
