// User-entered processing intent, not a simulated thermal or microstructure history.
const types = {solution: 'Solution treat', anneal: 'Anneal', age: 'Age', quench: 'Quench', ramp: 'Heat / cool', hold: 'Hold'};
export const processingMarkup = `
  <div class="processing-inputs two-col"><div><label for="opt-route">Initial creation</label><select id="opt-route" required><option value="">Choose a route</option><option>Sand cast</option><option>Die cast</option><option>Investment cast</option><option>Continuous cast</option><option>Arc melted</option><option>Induction melted</option><option>Forged</option><option>Extruded</option><option>Hot rolled</option><option>Powder metallurgy</option><option>Additively manufactured</option></select></div><div><label for="process-start-temperature">Starting temperature (°C)</label><input id="process-start-temperature" type="number" min="-273.14" max="3000" step="any" value="25" required></div></div>
  <div class="opt-rule-heading"><h3>Post-processing</h3><div class="thermal-add"><label class="visually-hidden" for="thermal-add-type">New thermal step</label><select id="thermal-add-type">${Object.entries(types).map(([value, name]) => `<option value="${value}">${name}</option>`).join('')}</select><button class="glass-button" type="button" id="thermal-add">+ Add step</button></div></div>
  <div class="thermal-chart"><svg id="thermal-plot" viewBox="0 0 900 320" role="img" aria-label="Entered temperature schedule, temperature in degrees Celsius against time in minutes"></svg><p class="fine">Entered schedule · linear ramps, not a thermal simulation</p></div>
  <div id="thermal-steps"></div><p class="fine" id="thermal-empty">No thermal steps added.</p>
  <div class="two-col cold-work"><div><label for="cold-work-method">Final work hardening</label><select id="cold-work-method"><option value="none">None</option><option value="rolling">Cold rolling</option><option value="drawing">Cold drawing</option><option value="other">Other cold work</option></select></div><div><label for="cold-work-reduction">Reduction (%)</label><input id="cold-work-reduction" type="number" min="0.000001" max="99.999999" step="any" disabled required aria-describedby="reduction-basis"><p class="fine" id="reduction-basis">Thickness reduction</p></div></div>
  <details class="advanced"><summary>Evaluation conditions & notes</summary><div class="two-col"><div><label for="opt-temperature">Property evaluation temperature (K)</label><input id="opt-temperature" type="number" min="1" max="6000" step="any" value="298.15" required></div><div><label for="opt-pressure">Pressure (Pa)</label><input id="opt-pressure" type="number" min="1" max="1000000000" step="any" value="101325" required></div></div><label for="opt-condition-notes">Processing notes (optional)</label><textarea id="opt-condition-notes" rows="3" maxlength="2000"></textarea></details>`;

export function initProcessing(root, onChange) {
  const $ = id => document.getElementById(id);
  const container = $('thermal-steps');
  let serial = 0;
  const rows = () => [...container.children];
  const format = value => Number(value).toLocaleString(undefined, {maximumSignificantDigits: 8});
  function readSchedule() {
    return rows().map(row => ({type: row.querySelector('.thermal-type').value,
      target: Number(row.querySelector('.thermal-target').value),
      ramp: Number(row.querySelector('.thermal-ramp').value),
      hold: Number(row.querySelector('.thermal-hold').value)}));
  }
  function redraw() {
    rows().forEach((row, i) => {
      row.querySelector('.thermal-number').textContent = i + 1;
      row.querySelector('[data-move="-1"]').disabled = i === 0;
      row.querySelector('[data-move="1"]').disabled = i === rows().length - 1;
    });
    $('thermal-empty').hidden = rows().length > 0;
    const invalid = [...container.querySelectorAll('input')].some(input => !input.disabled && !input.checkValidity()) || !$('process-start-temperature').checkValidity();
    const points = [[0, Number($('process-start-temperature').value)]];
    if (!invalid) for (const item of readSchedule()) {
      points.push([points.at(-1)[0] + item.ramp, item.target]);
      if (item.hold) points.push([points.at(-1)[0] + item.hold, item.target]);
    }
    const maxTime = Math.max(1, points.at(-1)[0]);
    const minTemp = Math.floor((Math.min(...points.map(p => p[1])) - 25) / 25) * 25;
    const maxTemp = Math.max(minTemp + 100, Math.ceil((Math.max(...points.map(p => p[1])) + 25) / 25) * 25);
    const plotWidth = Math.max(330, Math.min(900, $('thermal-plot').clientWidth || 900));
    const left = 60, right = plotWidth - 18, center = (left + right) / 2;
    const x = time => left + time / maxTime * (right - left);
    const y = temp => 240 - (temp - minTemp) / (maxTemp - minTemp) * 210;
    const divisions = plotWidth < 500 ? 2 : 4;
    const tick = value => Number(value).toLocaleString(undefined, {maximumFractionDigits: 2});
    const grid = Array.from({length: divisions + 1}, (_, i) => {
      const t = maxTime * i / divisions, temp = minTemp + (maxTemp - minTemp) * i / divisions;
      return `<path d="M${left} ${y(temp)}H${right} M${x(t)} 30V240" class="thermal-grid"/><text x="${left - 10}" y="${y(temp) + 4}" text-anchor="end">${tick(temp)}</text><text x="${x(t)}" y="263" text-anchor="middle">${tick(t)}</text>`;
    }).join('');
    $('thermal-plot').setAttribute('viewBox', `0 0 ${plotWidth} 300`);
    $('thermal-plot').innerHTML = `<title>Entered thermal schedule</title><desc>${invalid ? 'Complete the thermal step inputs to show the schedule.' : `Starting at ${format(points[0][1])} degrees Celsius; ${rows().length} thermal steps over ${format(points.at(-1)[0])} minutes.`}</desc>${grid}<text x="${left}" y="17">Temperature (°C)</text><text x="${center}" y="290" text-anchor="middle">Time (min)</text>${invalid ? `<text x="${center}" y="140" text-anchor="middle">Complete the step inputs</text>` : `<polyline points="${points.map(([t, temp]) => `${x(t)},${y(temp)}`).join(' ')}" class="thermal-line"/>${points.map(([t, temp]) => `<circle cx="${x(t)}" cy="${y(temp)}" r="4"/>`).join('')}`}`;

  }
  function updateRow(row) {
    const type = row.querySelector('.thermal-type').value;
    const hold = row.querySelector('.thermal-hold');
    hold.disabled = ['quench', 'ramp'].includes(type);
    hold.closest('div').hidden = hold.disabled;
    if (hold.disabled) hold.value = 0;
    else if (hold.value === '0') hold.value = '';
    row.querySelector('.thermal-ramp').min = ['quench', 'ramp'].includes(type) ? '0.000001' : '0';
  }
  function addStep() {
    const id = ++serial, type = $('thermal-add-type').value;
    const row = document.createElement('div'); row.className = 'thermal-step';
    row.innerHTML = `<span class="thermal-number"></span><div><label for="thermal-type-${id}">Treatment</label><select id="thermal-type-${id}" class="thermal-type">${Object.entries(types).map(([value, name]) => `<option value="${value}">${name}</option>`).join('')}</select></div><div><label for="thermal-target-${id}">Target (°C)</label><input id="thermal-target-${id}" class="thermal-target" type="number" min="-273.14" max="3000" step="any" required></div><div><label for="thermal-ramp-${id}">Ramp / cooling (min)</label><input id="thermal-ramp-${id}" class="thermal-ramp" type="number" min="0" step="any" value="0" required></div><div><label for="thermal-hold-${id}">Hold (min)</label><input id="thermal-hold-${id}" class="thermal-hold" type="number" min="0.000001" step="any" required></div><div class="thermal-row-actions"><button type="button" class="small-button" data-move="-1" aria-label="Move thermal step up">↑</button><button type="button" class="small-button" data-move="1" aria-label="Move thermal step down">↓</button><button type="button" class="small-button thermal-remove" aria-label="Remove thermal step">×</button></div>`;
    row.querySelector('.thermal-type').value = type;
    row.querySelector('.thermal-type').addEventListener('change', () => updateRow(row));
    row.querySelector('.thermal-remove').addEventListener('click', () => { row.remove(); redraw(); onChange(); $('thermal-add').focus(); });
    row.querySelectorAll('[data-move]').forEach(button => button.addEventListener('click', () => {
      if (button.dataset.move === '-1') container.insertBefore(row, row.previousElementSibling);
      else container.insertBefore(row.nextElementSibling, row);
      redraw(); onChange(); button.focus();
    }));
    container.append(row); updateRow(row); redraw(); onChange(); row.querySelector('.thermal-target').focus();
  }
  $('thermal-add').addEventListener('click', addStep);
  $('cold-work-method').addEventListener('change', () => {
    const method = $('cold-work-method').value;
    $('cold-work-reduction').disabled = method === 'none';
    $('reduction-basis').textContent = method === 'drawing' ? 'Cross-sectional area reduction' : method === 'other' ? 'Reduction basis: specify in processing notes' : 'Thickness reduction';
  });
  root.addEventListener('input', redraw); root.addEventListener('change', redraw);
  window.addEventListener('resize', redraw);
  redraw();
  return {redraw, readSchedule, summary() { return {
    route: $('opt-route').selectedOptions[0].textContent,
    start: Number($('process-start-temperature').value),
    events: readSchedule().map(item => ({...item, label: types[item.type]})),
    work: $('cold-work-method').value === 'none' ? 'None' : `${$('cold-work-method').selectedOptions[0].textContent} · ${format($('cold-work-reduction').value)}% ${$('cold-work-method').value === 'drawing' ? 'area' : $('cold-work-method').value === 'rolling' ? 'thickness' : ''} reduction`,
  }; }};
}
