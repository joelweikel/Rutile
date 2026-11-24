const palette = ['#83a8bd', '#c99b68', '#769e91', '#ae91bc', '#bb7876', '#a6ad66', '#759acb', '#bd8bad', '#c8ae86', '#91bac0'];
const world = {width: 900, height: 440};

export function microstructureMarkup(id) {
  return `<section id="${id}" class="microstructure" aria-labelledby="${id}-heading">
    <div class="micro-heading"><h3 id="${id}-heading">Microstructure</h3><span class="micro-badge">Schematic</span></div>
    <div class="micro-layout">
      <div class="micro-view">
        <canvas tabindex="0" aria-label="Microstructure schematic" aria-describedby="${id}-instructions ${id}-note"></canvas>
        <p id="${id}-instructions" class="visually-hidden">Scroll or use plus and minus to zoom. Drag or use the arrow keys to pan. Press Home to reset.</p>
        <div class="micro-zoom" aria-label="Zoom controls">
          <button type="button" data-zoom="out" aria-label="Zoom out">−</button>
          <button type="button" data-zoom="reset" aria-label="Reset zoom">1×</button>
          <button type="button" data-zoom="in" aria-label="Zoom in">+</button>
        </div>
      </div>
      <div class="micro-controls">
        <p class="fine micro-note" id="${id}-note"></p>
        <ul class="micro-legend" aria-label="Phase colors"></ul>
        <label for="${id}-size">Illustrative grain size</label>
        <select id="${id}-size" data-grain-size><option value="fine">Fine</option><option value="medium" selected>Medium</option><option value="coarse">Coarse</option></select>
        <fieldset>
          <legend>Illustrative layers</legend>
          <label><input type="checkbox" data-layer="spinodal"> Spinodal regions</label>
          <label><input type="checkbox" data-layer="boundary"> Boundary precipitates</label>
          <label><input type="checkbox" data-layer="interior"> Intragranular precipitates</label>
        </fieldset>
      </div>
    </div>
    <p class="fine micro-empty" hidden></p>
  </section>`;
}

function randomFrom(seed) {
  return () => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed / 4294967296;
  };
}

function cutCell(vertices, seed, other) {
  const dx = other.x - seed.x, dy = other.y - seed.y;
  const x = (seed.x + other.x) / 2, y = (seed.y + other.y) / 2;
  const edge = point => (point.x - x) * dx + (point.y - y) * dy;
  const result = [];
  let before = vertices.at(-1), distance = edge(before);
  for (const point of vertices) {
    const nextDistance = edge(point);
    if ((distance < 0) !== (nextDistance < 0)) {
      const t = distance / (distance - nextDistance);
      result.push({x: before.x + t * (point.x - before.x), y: before.y + t * (point.y - before.y)});
    }
    if (nextDistance <= 0) result.push(point);
    before = point;
    distance = nextDistance;
  }
  return result;
}

function buildGrains(size) {
  return grainSection(world, {fine: 15, medium: 10, coarse: 6}[size]);
}

export function grainSection({width, height}, columns) {
  const rows = Math.max(1, Math.round(columns * height / width));
  const seeds = [], random = randomFrom(741);
  for (let y = 0; y < rows; y++) {
    for (let x = 0; x < columns; x++) {
      seeds.push({
        x: (x + .2 + random() * .6) * width / columns,
        y: (y + .2 + random() * .6) * height / rows,
        shade: random(),
      });
    }
  }
  return seeds.map(seed => {
    let vertices = [{x: 0, y: 0}, {x: width, y: 0}, {x: width, y: height}, {x: 0, y: height}];
    for (const other of seeds) {
      if (other !== seed) vertices = cutCell(vertices, seed, other);
    }
    const outline = new Path2D();
    outline.moveTo(vertices[0].x, vertices[0].y);
    for (const point of vertices.slice(1)) outline.lineTo(point.x, point.y);
    outline.closePath();
    return {...seed, vertices, outline};
  });
}

function spinodalTile() {
  const tile = document.createElement('canvas');
  tile.width = tile.height = 120;
  const ctx = tile.getContext('2d'), raster = ctx.createImageData(tile.width, tile.height);
  const angle = (x, periods) => x * 2 * Math.PI * periods / tile.width;
  for (let y = 0; y < tile.height; y++) {
    for (let x = 0; x < tile.width; x++) {
      const field = Math.sin(angle(x, 8) + .85 * Math.sin(angle(y, 4))) +
        Math.sin(angle(y, 7) + .85 * Math.sin(angle(x, 3))) +
        .5 * Math.sin(angle(x + y, 5));
      const index = 4 * (y * tile.width + x);
      raster.data.set([49, 201, 169, Math.round(105 * Math.max(0, Math.min(1, (field + .15) * 2)))], index);
    }
  }
  ctx.putImageData(raster, 0, 0);
  return tile;
}

export function initMicrostructure(element) {
  const canvas = element.querySelector('canvas'), ctx = canvas.getContext('2d');
  const grainSize = element.querySelector('[data-grain-size]'), layers = [...element.querySelectorAll('[data-layer]')];
  const legend = element.querySelector('.micro-legend'), empty = element.querySelector('.micro-empty');
  const layout = element.querySelector('.micro-layout'), note = element.querySelector('.micro-note');
  const zoomButtons = element.querySelector('.micro-zoom');
  const grainTile = ctx?.createPattern(spinodalTile(), 'repeat');
  let grains = buildGrains(grainSize.value), solid = [], frame = 0;
  let zoom = 1, panX = 0, panY = 0, drag = null;

  function draw() {
    frame = 0;
    const {clientWidth: width, clientHeight: height} = canvas;
    if (!ctx || !width || !height || !solid.length) return;
    const dpr = window.devicePixelRatio || 1;
    const physicalWidth = Math.round(width * dpr), physicalHeight = Math.round(height * dpr);
    if (canvas.width !== physicalWidth || canvas.height !== physicalHeight) {
      canvas.width = physicalWidth;
      canvas.height = physicalHeight;
    }
    const scale = Math.max(width / world.width, height / world.height) * zoom;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    ctx.translate(width / 2 + panX, height / 2 + panY);
    ctx.scale(scale, scale);
    ctx.translate(-world.width / 2, -world.height / 2);
    const enabled = new Set(layers.filter(input => input.checked).map(input => input.dataset.layer));
    const random = randomFrom(1948);
    grains.forEach((grain, index) => {
      const phase = solid[(index * 7 + Math.floor(index / solid.length)) % solid.length];
      ctx.fillStyle = phase.color;
      ctx.fill(grain.outline);
      ctx.fillStyle = `rgba(13,27,39,${.12 + grain.shade * .41})`;
      ctx.fill(grain.outline);
      if (enabled.has('spinodal') && index % 7 === 2) {
        ctx.fillStyle = grainTile;
        ctx.fill(grain.outline);
      }
      if (enabled.has('interior')) {
        ctx.save();
        ctx.clip(grain.outline);
        ctx.strokeStyle = '#d5baffbb';
        ctx.lineWidth = 1.6;
        ctx.beginPath();
        for (let i = 0; i < 13; i++) {
          const span = Math.sqrt(world.width * world.height / grains.length);
          const x = grain.x + (random() - .5) * span, y = grain.y + (random() - .5) * span;
          const length = 2 + random() * 5, angle = 2.5 * grain.shade + .35 * random();
          ctx.moveTo(x, y);
          ctx.lineTo(x + Math.cos(angle) * length, y + Math.sin(angle) * length);
        }
        ctx.stroke();
        ctx.restore();
      }
    });
    ctx.strokeStyle = '#13232e';
    ctx.lineWidth = 1.25;
    grains.forEach(grain => ctx.stroke(grain.outline));
    if (enabled.has('boundary')) {
      ctx.fillStyle = '#ffce8d';
      grains.forEach((grain, index) => {
        grain.vertices.forEach((point, i) => {
          const next = grain.vertices[(i + 1) % grain.vertices.length];
          if ((index + i) % 3 || Math.hypot(next.x - point.x, next.y - point.y) < 19) return;
          for (const portion of [.31, .54, .71]) {
            ctx.beginPath();
            ctx.arc(point.x + (next.x - point.x) * portion, point.y + (next.y - point.y) * portion, 1.75, 0, 2 * Math.PI);
            ctx.fill();
          }
        });
      });
    }
  }

  function redraw() {
    if (!frame) frame = requestAnimationFrame(draw);
  }

  function limitPan() {
    const width = canvas.clientWidth, height = canvas.clientHeight;
    const scale = Math.max(width / world.width, height / world.height) * zoom;
    const maxX = Math.max(0, (world.width * scale - width) / 2);
    const maxY = Math.max(0, (world.height * scale - height) / 2);
    panX = Math.min(maxX, Math.max(-maxX, panX));
    panY = Math.min(maxY, Math.max(-maxY, panY));
  }

  function changeZoom(value, x = 0, y = 0) {
    const next = Math.max(1, Math.min(8, value));
    if (next === zoom) return;
    panX = x - (x - panX) * next / zoom;
    panY = y - (y - panY) * next / zoom;
    zoom = next;
    limitPan();
    zoomButtons.querySelector('[data-zoom="reset"]').textContent = `${Math.round(zoom * 10) / 10}×`;
    canvas.classList.toggle('micro-zoomed', zoom > 1);
    redraw();
  }

  function reset() {
    panX = panY = 0;
    changeZoom(1);
    redraw();
  }

  function setPhases(next) {
    const phases = next.map((phase, i) => ({...phase, color: palette[i % palette.length]}));
    solid = phases.filter(phase => !/^(LIQUID|GAS)(:|$)/i.test(phase.phase || phase.label));
    // Give rare phases a visible color swatch without encoding molar fraction as area.
    legend.replaceChildren(...phases.map(phase => {
      const item = document.createElement('li'), swatch = document.createElement('span');
      swatch.className = 'phase-swatch';
      swatch.style.backgroundColor = phase.color;
      item.append(swatch, phase.display_name ? `${phase.display_name} (${phase.label})` : phase.label);
      if (Number.isFinite(phase.fraction)) {
        item.append(` · ${(100 * phase.fraction).toLocaleString(undefined, {maximumSignificantDigits: 4})} mol%`);
      }
      return item;
    }));
    empty.hidden = Boolean(solid.length);
    layout.hidden = !solid.length;
    empty.textContent = 'Grain view unavailable. The final equilibrium has no solid phases.';
    if (solid.length) {
      note.textContent = phases.length === solid.length
        ? 'Calculated phase identities. Geometry and colored area are illustrative.'
        : 'Calculated phase identities. The schematic shows only solids, with illustrative geometry and area.';
    }
    reset();
  }

  grainSize.addEventListener('change', () => {
    grains = buildGrains(grainSize.value);
    redraw();
  });
  layers.forEach(input => input.addEventListener('change', redraw));
  zoomButtons.addEventListener('click', event => {
    const action = event.target.closest('[data-zoom]')?.dataset.zoom;
    if (action === 'in') changeZoom(zoom * 1.35);
    if (action === 'out') changeZoom(zoom / 1.35);
    if (action === 'reset') reset();
  });
  canvas.addEventListener('wheel', event => {
    if (event.ctrlKey || event.metaKey || !event.deltaY || (zoom === 1 && event.deltaY > 0)) return;
    event.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const delta = event.deltaMode === 0 ? event.deltaY : event.deltaY * 16;
    changeZoom(zoom * Math.exp(-Math.max(-240, Math.min(240, delta)) * .002),
      event.clientX - rect.left - rect.width / 2, event.clientY - rect.top - rect.height / 2);
  }, {passive: false});
  canvas.addEventListener('keydown', event => {
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    const pans = {ArrowLeft: [35, 0], ArrowRight: [-35, 0], ArrowUp: [0, 35], ArrowDown: [0, -35]};
    if (event.key === '+' || event.key === '=') changeZoom(zoom * 1.35);
    else if (event.key === '-') changeZoom(zoom / 1.35);
    else if (event.key === 'Home') reset();
    else if (Object.hasOwn(pans, event.key)) {
      panX += pans[event.key][0];
      panY += pans[event.key][1];
      limitPan();
      redraw();
    } else return;
    event.preventDefault();
  });
  canvas.addEventListener('pointerdown', event => {
    if (event.button !== 0 || zoom <= 1 || drag) return;
    canvas.setPointerCapture(event.pointerId);
    drag = {id: event.pointerId, x: event.clientX, y: event.clientY};
  });
  canvas.addEventListener('pointermove', event => {
    if (!drag || drag.id !== event.pointerId) return;
    panX += event.clientX - drag.x;
    panY += event.clientY - drag.y;
    drag.x = event.clientX;
    drag.y = event.clientY;
    limitPan();
    redraw();
  });
  canvas.addEventListener('lostpointercapture', () => { drag = null; });
  new ResizeObserver(() => {
    limitPan();
    redraw();
  }).observe(canvas);
  return {setPhases};
}
