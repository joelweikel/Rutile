const titles = {temperature_change: 'Temperature change', anneal: 'Anneal', quench: 'Quench', cold_work: 'Cold work'};
const media = {water: 'Water', oil: 'Oil', air: 'Air', brine: 'Brine'};
const kelvinOffset = 273.15;
const number = value => Number(value).toLocaleString(undefined, {maximumFractionDigits: 3});
const degrees = temperature => `${number(temperature)} °C`;

const celsius = temperature => temperature === null ? '' : Math.round((temperature - kelvinOffset) * 1e9) / 1e9;

export function processingScheduleMarkup(prefix = '', {initial = 298.15, melt = 1073.15, final = 298.15, route} = {}) {
  return `
  <div class="processing-layout">
    <figure class="thermal-chart">
      <figcaption><h3>Temperature schedule</h3><span class="fine">Event sequence</span></figcaption>
      <svg class="thermal-plot" id="${prefix}thermal-plot" role="img" aria-label="Planned temperature by processing event"></svg>
      <p class="fine" id="${prefix}thermal-selection"></p>
    </figure>
    <section class="process-sequence" aria-labelledby="${prefix}sequence-heading">
      <div class="sequence-heading"><h3 id="${prefix}sequence-heading">Events</h3>
        <details class="process-add" id="${prefix}process-add"><summary>+ Add event</summary>
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
      <label for="${prefix}opt-route">Starting route</label>
      <select id="${prefix}opt-route"><option value="arc_melting">Arc melt, then cool</option><option value="heat_treatment" ${route === 'heat_treatment' ? 'selected' : ''}>Start with solid alloy</option></select>
      <details id="${prefix}process-initial" class="process-event"><summary><span>Initial state</span><span class="event-value"></span></summary>
        <div class="event-fields"><div><label for="${prefix}process-start-temperature">Initial temperature (°C)</label><input id="${prefix}process-start-temperature" type="number" min="0" max="2226.85" step="any" value="${celsius(initial)}" required></div></div>
      </details>
      <details id="${prefix}process-melting" class="process-event"><summary><span>Arc melt &amp; cool</span><span class="event-value"></span></summary>
        <div class="event-fields"><div><label for="${prefix}process-melt-temperature">Melt temperature (°C)</label><input id="${prefix}process-melt-temperature" type="number" min="0" max="3726.85" step="any" value="${celsius(melt)}" required></div>
        <div><label for="${prefix}opt-temperature">Cool to (°C)</label><input id="${prefix}opt-temperature" type="number" min="0" max="2226.85" step="any" value="${celsius(final)}" required></div></div>
      </details>
      <div id="${prefix}process-events"></div>
    </section>
  </div>`;
}

export function describeEvent(event) {
  const temperature = degrees(event.temperature_k - kelvinOffset);
  const title = titles[event.kind];
  switch (event.kind) {
    case 'temperature_change':
      return [title, temperature + (event.duration_s ? ` · ${number(event.duration_s / 60)} min` : '')];
    case 'anneal':
      return [title, `${temperature} · ${number(event.hold_s / 60)} min hold`];
    case 'quench':
      return [`${media[event.medium]} quench`, temperature];
    case 'cold_work':
      return [title, `${number(event.reduction_pct)}% reduction`];
  }
}

export function restoreScheduleEvents(value = []) {
  if (!Array.isArray(value) || value.length > 24) throw new Error('The workflow has an invalid processing schedule.');
  const scalar = value => Number.isFinite(value) ? value : null;
  return value.map(event => {
    const kind = event?.kind;
    if (typeof kind !== 'string' || !Object.hasOwn(titles, kind)) throw new Error('The workflow has an unknown processing event.');
    if (kind === 'cold_work') return {kind, reduction_pct: scalar(event.reduction_pct)};
    const temperature_k = scalar(event.temperature_k);
    if (kind === 'quench') {
      if (typeof event.medium !== 'string' || !Object.hasOwn(media, event.medium)) throw new Error('The workflow has an unknown quench medium.');
      return {kind, temperature_k, medium: event.medium};
    }
    return kind === 'anneal' ? {kind, temperature_k, hold_s: scalar(event.hold_s)} :
      {kind, temperature_k, duration_s: scalar(event.duration_s)};
  });
}

export function scheduleIssue({route, initial, melt, final, pressure, points, events}) {
  const validTemperature = (value, max) => Number.isFinite(value) && value >= 273.15 && value <= max;
  if (!validTemperature(initial, 2500)) return 'Set a valid initial temperature.';
  if (!Number.isFinite(pressure) || pressure <= 0 || pressure > 1e9) return 'Set a valid pressure (Pa).';
  const arc = route === 'arc_melting';
  if (arc) {
    if (!validTemperature(melt, 4000) || !validTemperature(final, 2500)) return 'Set valid melt and cool-to temperatures.';
    if (melt <= Math.max(initial, final)) return 'Melt temperature must exceed the initial and cool-to temperatures.';
    if (!Number.isInteger(points) || points < 3 || points > 61) return 'Set 3–61 cooling points.';
  } else if (!events.length) return 'Add a processing event.';
  let previous = arc ? final : initial;
  for (const [index, event] of events.entries()) {
    const label = `Event ${index + 1}`;
    if (event.kind === 'cold_work') {
      if (!(event.reduction_pct > 0 && event.reduction_pct < 100)) return `${label} needs a thickness reduction between 0 and 100%.`;
      if (index !== events.length - 1) return 'Cold work must be the last event.';
      continue;
    }
    if (!validTemperature(event.temperature_k, event.kind === 'temperature_change' ? 4000 : 2500)) {
      return `${label} needs a valid temperature.`;
    }
    if (event.kind === 'anneal' && !(event.hold_s > 0)) return `${label} needs a positive hold duration.`;
    if (event.kind === 'temperature_change' && event.duration_s !== null && !(event.duration_s > 0)) {
      return `${label} needs a positive duration or an empty duration field.`;
    }
    if (event.kind === 'quench' && event.temperature_k >= previous) return `${label} must quench below the previous setpoint.`;
    previous = event.temperature_k;
  }
  return null;
}

export function schedulePoints({route, initial, melt, final, events}) {
  const temperature = value => value >= kelvinOffset && value <= 4000 ? celsius(value) : NaN;
  const points = [{title: 'Start', temperature: temperature(initial), key: 'process-initial'}];
  if (route === 'arc_melting') points.push(
    {title: 'Melt', temperature: temperature(melt), key: 'process-melting'},
    {title: 'Cool', temperature: temperature(final), key: 'process-melting'},
  );
  events.forEach((event, index) => {
    const value = event.kind === 'cold_work' ? points.at(-1).temperature : temperature(event.temperature_k);
    points.push({title: String(index + 1), temperature: value, key: index, kind: event.kind});
    if (event.kind === 'anneal') points.push({title: '', temperature: value, key: index, kind: 'hold'});
  });
  return points;
}

export function renderSchedulePlot(plot, points, {compact = false, selected} = {}) {
  const width = compact ? 204 : Math.max(220, Math.round(plot.clientWidth || 620));
  const height = compact ? 91 : Math.round(plot.clientHeight || 265);
  const short = height <= 150;
  const left = 41, right = width - 18, top = short ? 20 : 33, bottom = height - (short ? 23 : 47);
  const values = points.map(point => point.temperature).filter(Number.isFinite);
  const maximum = Math.max(100, ...values);
  const target = maximum / (short ? 2 : 4);
  const range = 10 ** Math.floor(Math.log10(target));
  const interval = [1, 2, 2.5, 5, 10].map(scale => range * scale).find(value => value >= target);
  const upper = interval * Math.ceil(maximum / interval);
  const y = value => bottom - (value / upper) * (bottom - top);
  const x = index => left + 8 + (right - left - 11) * index / Math.max(1, points.length - 1);
  const ticks = Array.from({length: Math.round(upper / interval) + 1}, (_, i) => i * interval);
  const stride = Math.max(1, Math.ceil((points.length - 1) * 25 / (right - left)));
  plot.setAttribute('viewBox', `0 0 ${width} ${height}`);
  plot.innerHTML = `<title>Planned temperature by event. Horizontal spacing indicates sequence.</title>
    <text x="4" y="13">°C</text>
    ${ticks.map(value => `<path class="thermal-grid" d="M${left} ${y(value)}H${right}"/><text x="${left - 7}" y="${y(value) + 4}" text-anchor="end">${value}</text>`).join('')}
    ${points.map((point, i) => i && Number.isFinite(point.temperature) && Number.isFinite(points[i - 1].temperature) ?
      `<polyline class="thermal-line ${point.kind || ''}" points="${x(i - 1)},${y(points[i - 1].temperature)} ${x(i)},${y(point.temperature)}"/>` : '').join('')}
    ${points.map((point, i) => {
      const active = point.key === selected;
      const showLabel = point.title && (active || i % stride === 0);
      return `${showLabel ? `<text class="thermal-x-label" x="${x(i)}" y="${bottom + (short ? 18 : 24)}" text-anchor="middle">${point.title}</text>` : ''}
        ${Number.isFinite(point.temperature) ? `<circle ${compact ? '' : `data-point="${i}"`} cx="${x(i)}" cy="${y(point.temperature)}" r="${active ? 6 : 3.5}" class="${active ? 'thermal-active' : ''}"><title>${degrees(point.temperature)}</title></circle>` : ''}`;
    }).join('')}`;
}

export function initProcessingEvents(onChange, {root = document, prefix = '', settings, live = false} = {}) {
  const $ = id => root.querySelector(`#${prefix}${id}`);
  const layout = $('process-events').closest('.processing-layout');
  const events = $('process-events'), menu = $('process-add'), plot = $('thermal-plot');
  const initial = $('process-start-temperature'), melt = $('process-melt-temperature'), cool = $('opt-temperature');
  const isArc = () => $('opt-route').value === 'arc_melting';
  const rows = () => [...events.children];
  let nextId = 0, selected = null;

  function readEvent(row) {
    const kind = row.dataset.kind;
    if (kind === 'cold_work') return {kind, reduction_pct: row.querySelector('input').valueAsNumber};
    const event = {kind, temperature_k: row.querySelector('.event-temperature').valueAsNumber + kelvinOffset};
    if (kind === 'quench') event.medium = row.querySelector('select').value;
    if (kind === 'anneal') event.hold_s = row.querySelector('.event-duration').valueAsNumber * 60;
    if (kind === 'temperature_change') {
      const duration = row.querySelector('.event-duration').valueAsNumber;
      event.duration_s = Number.isFinite(duration) ? duration * 60 : null;
    }
    return event;
  }

  function readSchedule() {
    return {route: $('opt-route').value, initial: initial.valueAsNumber + kelvinOffset,
      melt: melt.valueAsNumber + kelvinOffset, final: cool.valueAsNumber + kelvinOffset, events: rows().map(readEvent)};
  }

  const rowFor = key => typeof key === 'number' ? rows()[key] : $(key);

  function renderChart() {
    const points = schedulePoints(readSchedule());
    renderSchedulePlot(plot, points, {selected: points.find(point => rowFor(point.key) === selected)?.key});
    const description = selected && [...selected.querySelector('summary').children]
      .map(item => item.textContent.trim()).filter(Boolean).join(' · ');
    $('thermal-selection').textContent = description || (points.length === 1 ? 'Add an event to build the schedule.' : 'Select an event to inspect its setpoint.');
  }

  function redraw() {
    $('process-melting').hidden = !isArc();
    melt.disabled = cool.disabled = !isArc();
    if (!isArc() && selected === $('process-melting')) selected = null;
    $('process-initial').querySelector('.event-value').textContent = initial.validity.valid ? degrees(initial.valueAsNumber) : '';
    $('process-melting').querySelector('.event-value').textContent = melt.validity.valid && cool.validity.valid ?
      `${degrees(melt.valueAsNumber)} → ${degrees(cool.valueAsNumber)}` : '';
    const list = rows(), thermal = list.filter(row => row.dataset.kind !== 'cold_work');
    for (const row of list) {
      const event = readEvent(row);
      const [title, value] = describeEvent(event);
      const index = thermal.indexOf(row);
      row.querySelector('.event-title').textContent = `${list.indexOf(row) + 1}. ${title}`;
      row.querySelector('.event-value').textContent = [...row.querySelectorAll('input')].every(input => input.validity.valid) ? value : 'Set parameters';
      row.querySelector('[data-move="-1"]').disabled = index <= 0;
      row.querySelector('[data-move="1"]').disabled = index < 0 || index === thermal.length - 1;
    }
    menu.querySelectorAll('[data-add-event]').forEach(button => {
      button.disabled = list.length >= 24 || (button.dataset.addEvent === 'cold_work' && list.length > thermal.length);
    });
    renderChart();
  }

  function update() {
    redraw();
    onChange(readSchedule());
  }

  function add(kind, medium, saved) {
    const id = `${prefix}${++nextId}`, row = document.createElement('details');
    row.className = 'process-event';
    row.dataset.kind = kind;
    const work = kind === 'cold_work';
    const temperature = `<div><label for="event-temperature-${id}">${kind === 'quench' ? 'Target' : 'Setpoint'} (°C)</label><input id="event-temperature-${id}" class="event-temperature" type="number" min="0" max="${kind === 'temperature_change' ? 3726.85 : 2226.85}" step="any" ${kind === 'quench' ? 'value="25"' : 'placeholder="Enter temperature"'} required></div>`;
    const duration = `<div><label for="event-duration-${id}">${kind === 'anneal' ? 'Hold (min)' : 'Duration (min, optional)'}</label><input id="event-duration-${id}" class="event-duration" type="number" min="0.000001" step="any" ${kind === 'anneal' ? 'required' : ''}></div>`;
    const quenchMedium = `<div><label for="quench-medium-${id}">Medium</label><select id="quench-medium-${id}">${Object.entries(media).map(([key, name]) => `<option value="${key}" ${key === medium ? 'selected' : ''}>${name}</option>`).join('')}</select></div>`;
    row.innerHTML = `<summary><span class="event-title"></span><span class="event-value"></span></summary>
      <div class="event-fields">${work
        ? `<div><label for="event-reduction-${id}">Thickness reduction (%)</label><input id="event-reduction-${id}" type="number" min="0.000001" max="99.999999" step="any" required></div>`
        : temperature + (kind === 'quench' ? quenchMedium : duration)}
      </div>
      ${kind === 'anneal' ? '<p class="fine event-help">CALPHAD can screen phase stability. Choosing a hold time requires an annealing objective and a kinetic model.</p>' : ''}
      <div class="event-actions"><button type="button" data-move="-1" aria-label="Move event earlier" ${work ? 'hidden' : ''}>↑</button><button type="button" data-move="1" aria-label="Move event later" ${work ? 'hidden' : ''}>↓</button><button type="button" data-remove-event>Remove</button></div>`;
    events.insertBefore(row, saved || work ? null : events.querySelector('[data-kind="cold_work"]'));
    if (saved) {
      if (work) row.querySelector('input').value = saved.reduction_pct ?? '';
      else {
        row.querySelector('.event-temperature').value = celsius(saved.temperature_k);
        const durationField = row.querySelector('.event-duration');
        const seconds = saved.hold_s ?? saved.duration_s;
        if (durationField) durationField.value = seconds == null ? '' : seconds / 60;
      }
      return;
    }
    if (selected?.open) selected.open = false;
    selected = row;
    row.open = true;
    menu.open = false;
    menu.querySelector('.process-menu details').open = false;
    update();
    row.querySelector('input').focus();
  }

  menu.addEventListener('click', event => {
    const button = event.target.closest('[data-add-event]');
    if (button && !button.disabled) add(button.dataset.addEvent, button.dataset.medium);
  });
  menu.addEventListener('focusout', event => {
    if (event.relatedTarget && !menu.contains(event.relatedTarget)) menu.open = false;
  });
  menu.addEventListener('keydown', event => {
    if (event.key === 'Escape' && menu.open) {
      event.preventDefault();
      menu.open = false;
      menu.querySelector('summary').focus();
    }
  });
  layout.addEventListener('click', event => {
    if (menu.open && !menu.contains(event.target)) menu.open = false;
    const point = event.target.closest('[data-point]');
    if (point) {
      const row = rowFor(schedulePoints(readSchedule())[Number(point.dataset.point)].key);
      if (selected !== row && selected?.open) selected.open = false;
      selected = row;
      row.open = true;
      row.querySelector('summary').focus();
      renderChart();
    }
    const summary = event.target.closest('.process-event > summary');
    if (summary) {
      const row = summary.parentElement;
      if (selected !== row && selected?.open) selected.open = false;
      selected = row;
      renderChart();
    }
    const move = event.target.closest('[data-move]');
    const remove = event.target.closest('[data-remove-event]');
    if (move && !move.disabled) {
      const row = move.closest('.process-event');
      if (move.dataset.move === '-1') events.insertBefore(row, row.previousElementSibling);
      else events.insertBefore(row.nextElementSibling, row);
      update();
      (move.disabled ? row.querySelector('summary') : move).focus();
    }
    if (remove) {
      const row = remove.closest('.process-event');
      if (selected === row) selected = null;
      row.remove();
      update();
      menu.querySelector('summary').focus();
    }
  });
  layout.addEventListener('input', live ? update : redraw);
  layout.addEventListener('change', live ? update : redraw);
  const observer = new ResizeObserver(renderChart);
  observer.observe(plot);
  settings?.events.forEach(event => add(event.kind, event.medium, event));
  redraw();

  return {
    redraw,
    dispose() { observer.disconnect(); },
    issue() {
      if (isArc() && melt.valueAsNumber <= Math.max(initial.valueAsNumber, cool.valueAsNumber)) {
        return {message: 'The melt temperature must exceed the initial and cool-to temperatures.', field: melt};
      }
      if (!isArc() && !events.children.length) return {message: 'Add a processing event.', field: menu.querySelector('summary')};
      let temperature = isArc() ? cool.valueAsNumber : initial.valueAsNumber;
      for (const row of rows()) {
        const field = row.querySelector('.event-temperature');
        if (!field) continue;
        if (row.dataset.kind === 'quench' && field.valueAsNumber >= temperature) {
          return {message: 'The quench target must be colder than the previous setpoint.', field};
        }
        temperature = field.valueAsNumber;
      }
      return null;
    },
    request() {
      return {
        route: $('opt-route').value,
        initial_temperature_k: initial.valueAsNumber + kelvinOffset,
        ...(isArc() ? {melt_temperature_k: melt.valueAsNumber + kelvinOffset,
          final_temperature_k: cool.valueAsNumber + kelvinOffset} : {}),
        events: rows().map(readEvent),
      };
    },
  };
}
