const titles = {temperature_change: 'Temperature change', anneal: 'Anneal', quench: 'Quench', cold_work: 'Cold work'};
const media = {water: 'Water', oil: 'Oil', air: 'Air', brine: 'Brine'};
const kelvinOffset = 273.15;
const number = value => Number(value).toLocaleString(undefined, {maximumFractionDigits: 3});
const degrees = temperature => `${number(temperature)} °C`;

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

export function initProcessingEvents(onChange) {
  const $ = id => document.getElementById(id);
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

  function buildPoints() {
    const points = [{title: 'Start', temperature: initial.valueAsNumber, row: $('process-initial')}];
    if (isArc()) points.push(
      {title: 'Melt', temperature: melt.valueAsNumber, row: $('process-melting')},
      {title: 'Cool', temperature: cool.valueAsNumber, row: $('process-melting')},
    );
    rows().forEach((row, index) => {
      const event = readEvent(row), work = event.kind === 'cold_work';
      const hold = event.kind === 'anneal', title = String(index + 1);
      const temperature = work ? points.at(-1).temperature : row.querySelector('.event-temperature').valueAsNumber;
      points.push({title, temperature, row, kind: event.kind});
      if (hold) points.push({title: '', temperature, row, kind: 'hold'});
    });
    return points;
  }

  function renderChart() {
    const width = Math.max(240, Math.round(plot.clientWidth || 620)), height = 265;
    const left = 41, right = width - 18, top = 33, bottom = height - 47;
    const points = buildPoints();
    const values = points.map(point => point.temperature).filter(Number.isFinite);
    const maximum = Math.max(100, ...values);
    const range = 10 ** Math.floor(Math.log10(maximum / 4));
    const interval = [1, 2, 2.5, 5, 10].map(scale => range * scale).find(value => value >= maximum / 4);
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
        const active = point.row === selected;
        const showLabel = point.title && (active || i % stride === 0);
        return `${showLabel ? `<text class="thermal-x-label" x="${x(i)}" y="${bottom + 24}" text-anchor="middle">${point.title}</text>` : ''}
          ${Number.isFinite(point.temperature) ? `<circle data-point="${i}" cx="${x(i)}" cy="${y(point.temperature)}" r="${active ? 6 : 3.5}" class="${active ? 'thermal-active' : ''}"><title>${degrees(point.temperature)}</title></circle>` : ''}`;
      }).join('')}`;
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
    onChange();
  }

  function add(kind, medium) {
    const id = ++nextId, row = document.createElement('details');
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
    events.insertBefore(row, work ? null : events.querySelector('[data-kind="cold_work"]'));
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
      const row = buildPoints()[Number(point.dataset.point)].row;
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
  layout.addEventListener('input', redraw);
  layout.addEventListener('change', redraw);
  new ResizeObserver(renderChart).observe(plot);
  redraw();

  return {
    redraw,
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
