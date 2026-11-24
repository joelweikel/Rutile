import {appearanceModes, polishedReferences} from './alloy-phase-colors.js';
import {grainSection} from './microstructure.js';

export function readMicrostructure(raw) {
  try {
    const value = JSON.parse(raw);
    if (value?.kind !== 'microstructure' || value.schema_version !== 1 ||
        !['measured', 'modeled'].includes(value.origin) || typeof value.source !== 'string' ||
        typeof value.matrix_phase !== 'string' || !Array.isArray(value.samples) ||
        !value.samples.length || value.samples.length > 2000) return null;
    return value.samples.every(sample => Number.isFinite(sample?.time_s) && Number.isFinite(sample?.temperature_k) &&
      Array.isArray(sample.precipitates) && sample.precipitates.length <= 32 &&
      sample.precipitates.every(population => typeof population?.phase === 'string')) ? value : null;
  } catch { return null; }
}

export function importPrecipitationParameters(raw, filename) {
  if (!filename.toLowerCase().endsWith('.kdb')) {
    const value = JSON.parse(raw);
    if (!value || Array.isArray(value) || typeof value !== 'object') throw new Error('Choose a parameter JSON object.');
    return JSON.stringify(value, null, 2);
  }
  if (/<!DOCTYPE/i.test(raw)) throw new Error('Choose a KDB without a document type declaration.');
  const doc = new DOMParser().parseFromString(raw, 'application/xml');
  if (doc.querySelector('parsererror')) throw new Error('Choose an XML Pandat KDB file.');
  const alloys = doc.querySelectorAll('Alloy');
  if (alloys.length !== 1 || alloys[0].querySelectorAll('MatrixPhase').length !== 1) {
    throw new Error('Choose a KDB with one alloy and one matrix.');
  }
  const alloy = alloys[0];
  const phases = [...alloy.querySelectorAll('PrecipitatePhase')];
  if (!phases.length || phases.length > 8) throw new Error('Choose a KDB with one to eight precipitate phases.');
  function constant(element, type) {
    const value = element.querySelector(`ParameterTable Parameter[type="${type}"]`)?.getAttribute('value');
    return value && Number.isFinite(Number(value)) && Number(value) > 0 ? Number(value) : undefined;
  }
  const matrix = alloy.querySelector('MatrixPhase');
  return JSON.stringify({schema_version: 1, source: `Numeric parameter draft from ${filename}`,
    matrix_molar_volume_m3_mol_atoms: constant(matrix, 'Molar_Volume'),
    precipitates: phases.map(phase => ({
      phase: phase.getAttribute('name')?.toUpperCase(),
      interfacial_energy_j_m2: constant(phase, 'Interfacial_Energy'),
      molar_volume_m3_mol_atoms: constant(phase, 'Molar_Volume'),
    })),
  }, null, 2);
}

export function microstructureMarkup(result, esc, format, appearance, viewerSettings) {
  const value = result.microstructure;
  const index = value.samples.length - 1;
  const preset = result.settings?.preset?.id === 'matcalc-ni-gamma-prime-823k';
  const {colors, mode, etchant, conditions, source, references, hasEtchReference} = appearance;
  const phases = new Set([value.matrix_phase, ...value.samples.flatMap(sample => sample.precipitates.map(phase => phase.phase))]);
  const missing = [...phases].filter(phase => !Object.hasOwn(colors, phase));
  const note = mode === 'schematic' ? '' : mode === 'spectral'
    ? '<p class="fine">Spectral swatches apply to matched phase compositions. Gray indicates unavailable color.</p>' : mode === 'etched' && !hasEtchReference
    ? '<p class="fine studio-warning">Etched colors require the etchant, preparation and imaging conditions, and source in Phase Colors.</p>'
    : missing.length ? `<p class="fine studio-warning">Default colors shown for ${missing.map(esc).join(', ')}.</p>` : '';
  return `<figure class="studio-microstructure-figure">
      <canvas class="studio-microstructure-canvas" data-microstructure-canvas role="img"
        aria-label="Precipitate schematic"></canvas>
      <figcaption class="fine">Synthetic micrograph · ${mode === 'etched' && !hasEtchReference
        ? 'Etched reference pending' : appearanceModes[mode] ?? 'Spectral color'} · illustrative geometry</figcaption>
      <p class="fine studio-microstructure-empty" data-microstructure-empty hidden></p>
    </figure>
    ${viewerSettings ? `<label><input type="checkbox" data-field="grainBoundaries"
      ${viewerSettings.grainBoundaries ? 'checked' : ''}> Illustrative matrix grain boundaries</label>` : ''}
    ${index ? `<label>Sample time <input type="range" min="0" max="${index}" value="${index}" data-microstructure-sample
      aria-valuetext="${format(value.samples[index].time_s)} seconds"></label>` : ''}
    <p>${preset ? 'γ′ (Ni₃Al-type) · ' : ''}${swatch(value.matrix_phase, colors, true)}${esc(value.matrix_phase)} matrix · ${value.origin === 'measured' ? 'Measured' : 'Modeled'}
      ${value.pressure_pa == null ? '' : ` · ${format(value.pressure_pa)} Pa`}</p>
    ${note}
    <div data-microstructure-table>${microstructureSample(value.samples[index], esc, format, colors)}</div>
    <details><summary>Source and assumptions</summary><p>${esc(value.source)}</p>
      ${result.settings?.preset ? `<p>Preset · ${esc(result.settings.preset.id)}</p>
        <p>${esc(result.settings.preset.parameters.source)}</p>` : ''}
      ${result.settings?.parameter_overrides ? `<p>Override · ${esc(result.settings.parameter_overrides.source)}</p>` : ''}
      ${mode === 'etched' && hasEtchReference ? `<p>${esc(etchant)} · ${esc(conditions)} · ${esc(source)}</p>` : ''}
      ${mode === 'polished' ? Object.entries(references).filter(([phase]) => phases.has(phase)).map(([phase, id]) =>
        `<p>${esc(phase)} · <a href="${polishedReferences[id].url}" target="_blank" rel="noopener">${polishedReferences[id].label}</a> · approximate swatch</p>`).join('') : ''}
      ${result.assumptions?.map(note => `<p>${esc(note)}</p>`).join('') || ''}</details>`;
}

export function microstructureSample(sample, esc, format, colors) {
  const amount = (value, scale = 1) => Number.isFinite(value) ? format(value * scale) : '—';
  const composition = sample.matrix_composition_mole_fraction;
  return `<p>${format(sample.time_s)} s · ${format(sample.temperature_k)} K</p>
    ${composition ? `<p>Matrix (at.%) · ${Object.entries(composition).map(([element, value]) =>
      `${esc(element)} ${amount(value, 100)}`).join(' · ')}</p>` : ''}
    <table><thead><tr><th>Precipitate</th><th>Mean radius (nm)</th><th>Number density (m⁻³)</th>
      <th>vol.%</th></tr></thead><tbody>${sample.precipitates.map(phase =>
      `<tr><td>${swatch(phase.phase, colors)}${esc(phase.phase)}</td><td>${amount(phase.mean_radius_m, 1e9)}</td>
        <td>${Number.isFinite(phase.number_density_m3) ? phase.number_density_m3.toExponential(3) : '—'}</td>
        <td>${amount(phase.volume_fraction, 100)}</td></tr>`).join('')}</tbody></table>`;
}

const precipitateColors = ['#c4c8c3', '#a1b5bc', '#cbbcaa', '#a9a5ad', '#dedad2', '#b4b9a6'];
const sectionWidth = 320, sectionHeight = 192;
let texture;
let matrixGrains;

function phaseSeed(name) {
  let seed = 2166136261;
  for (const letter of name) seed = Math.imul(seed ^ letter.charCodeAt(0), 16777619) >>> 0;
  return seed;
}

export function phaseColor(name, colors = {}, matrix = false) {
  if (Object.hasOwn(colors, name)) return colors[name];
  return matrix ? '#565e63' : precipitateColors[phaseSeed(name) % precipitateColors.length];
}

function swatch(name, colors, matrix = false) {
  return `<span class="studio-microstructure-swatch" ${matrix ? 'data-matrix-swatch' : ''} aria-hidden="true"
    style="--phase-color:${phaseColor(name, colors, matrix)}"></span>`;
}

function seededRandom(seed) {
  return () => (seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0) / 4294967296;
}

function polishTexture() {
  if (texture) return texture;
  texture = document.createElement('canvas');
  texture.width = sectionWidth * 2;
  texture.height = sectionHeight * 2;
  const ctx = texture.getContext('2d');
  const image = ctx.createImageData(texture.width, texture.height);
  const random = seededRandom(48155);
  for (let i = 0; i < image.data.length; i += 4) {
    const grain = 128 + (random() + random() - 1) * 110;
    image.data[i] = image.data[i + 1] = image.data[i + 2] = grain;
    image.data[i + 3] = 255;
  }
  ctx.putImageData(image, 0, 0);
  return texture;
}

function drawMatrix(ctx, color) {
  ctx.fillStyle = color;
  ctx.fillRect(0, 0, sectionWidth, sectionHeight);
  const random = seededRandom(6524);
  for (let i = 0; i < 60; i += 1) {
    const x = random() * sectionWidth, y = random() * sectionHeight;
    const radius = 5 + random() ** 2 * 38;
    const tone = i % 2 ? '0,0,0' : '255,255,255';
    const gradient = ctx.createRadialGradient(x, y, 0, x, y, radius);
    gradient.addColorStop(0, `rgba(${tone},0.14)`);
    gradient.addColorStop(1, `rgba(${tone},0)`);
    ctx.fillStyle = gradient;
    ctx.fillRect(x - radius, y - radius, radius * 2, radius * 2);
  }
}

function drawMatrixGrains(ctx, mode) {
  matrixGrains ??= grainSection({width: sectionWidth, height: sectionHeight}, 5);
  const surface = mode === 'polished' ? 0.5 : 1;
  for (const {shade, outline} of matrixGrains) {
    ctx.fillStyle = shade > 0.5 ? '#ffffff' : '#000000';
    ctx.globalAlpha = surface * Math.abs(shade - 0.5) * 0.28;
    ctx.fill(outline);
  }
  ctx.strokeStyle = '#111517';
  ctx.globalAlpha = mode === 'etched' ? 0.31 : 0.21 * surface;
  ctx.lineWidth = mode === 'etched' ? 1.15 : 0.8;
  for (const {outline} of matrixGrains) ctx.stroke(outline);
  ctx.globalAlpha = 1;
}

function traceParticle(ctx, x, y, major, minor, angle) {
  const cos = Math.cos(angle), sin = Math.sin(angle);
  ctx.beginPath();
  for (let i = 0; i < 28; i += 1) {
    const theta = i * (2 * Math.PI / 28);
    const edge = 1 + 0.035 * Math.cos(3 * theta + angle) + 0.022 * Math.sin(7 * theta + angle);
    const a = Math.cos(theta) * major * edge, b = Math.sin(theta) * minor * edge;
    ctx.lineTo(x + a * cos - b * sin, y + a * sin + b * cos);
  }
  ctx.closePath();
}

function drawPopulations(ctx, populations, maximumRadius, colors) {
  const occupied = [];
  for (const phase of populations) {
    const ratio = Number.isFinite(phase.mean_radius_m) && phase.mean_radius_m > 0 && maximumRadius > 0
      ? phase.mean_radius_m / maximumRadius : 0.6;
    const radius = 5.7 * Math.max(0.24, ratio);
    const targetArea = sectionWidth * sectionHeight * phase.volume_fraction;
    const attempts = Math.min(2400, 24 + Math.ceil(12 * targetArea / (Math.PI * radius ** 2)));
    const random = seededRandom(phaseSeed(phase.phase));
    const color = phaseColor(phase.phase, colors);
    let area = 0;
    for (let i = 0; i < attempts && area < targetArea && occupied.length < 840; i += 1) {
      const x = random() * sectionWidth, y = random() * sectionHeight;
      // An off-center section through a sphere exposes a smaller cross section.
      const offset = random();
      const section = radius * Math.sqrt(1 - offset ** 2);
      const r = Math.max(0.45, section * (0.72 + 0.68 * random()));
      const minor = r * (0.8 + 0.2 * random());
      const angle = random() * Math.PI;
      if (occupied.some(dot => (dot.x - x) ** 2 + (dot.y - y) ** 2 < (dot.r + r + 0.25) ** 2)) continue;
      occupied.push({x, y, r});
      area += Math.PI * r * minor;
      traceParticle(ctx, x, y, r, minor, angle);
      ctx.globalAlpha = 1;
      ctx.strokeStyle = '#17191b50';
      ctx.lineWidth = 0.95;
      ctx.stroke();
      ctx.fillStyle = color;
      ctx.fill();
      ctx.globalAlpha = 0.16 * random();
      ctx.fillStyle = '#161a1d';
      ctx.fill();
    }
    ctx.globalAlpha = 1;
  }
}

export function maximumParticleRadius(value) {
  let maximum = 0;
  for (const sample of value.samples) for (const phase of sample.precipitates) {
    if (phase.volume_fraction > 0 && Number.isFinite(phase.mean_radius_m)) maximum = Math.max(maximum, phase.mean_radius_m);
  }
  return maximum;
}

export function renderMicrostructureCanvas(canvas, value, sample, maximumRadius, format, appearance, grainBoundaries = false) {
  const {colors, mode, hasEtchReference} = appearance;
  const populations = sample?.precipitates.filter(phase => Number.isFinite(phase.volume_fraction) && phase.volume_fraction > 0) || [];
  let message = '';
  if (!sample) message = 'Connect a result to preview the microstructure.';
  else if (populations.length === 0) {
    message = sample.precipitates.every(phase => phase.volume_fraction === 0)
      ? 'No resolved precipitates at this sample.' : 'Precipitate volume fractions are unavailable.';
  }
  canvas.setAttribute('aria-label', message || `Schematic at ${format(sample.time_s)} seconds. ${populations
    .map(phase => `${phase.phase} ${format(100 * phase.volume_fraction)} volume percent`).join(', ')}.`);

  const width = canvas.clientWidth || 204;
  const height = canvas.clientHeight || 122;
  const density = window.devicePixelRatio || 1;
  const pixelWidth = Math.round(width * density), pixelHeight = Math.round(height * density);
  if (canvas.width !== pixelWidth) canvas.width = pixelWidth;
  if (canvas.height !== pixelHeight) canvas.height = pixelHeight;
  const ctx = canvas.getContext('2d');
  if (!ctx) return message;
  ctx.setTransform(pixelWidth / sectionWidth, 0, 0, pixelHeight / sectionHeight, 0, 0);
  drawMatrix(ctx, phaseColor(value?.matrix_phase, colors, true));
  if (sample && grainBoundaries) drawMatrixGrains(ctx, mode === 'etched' && !hasEtchReference ? 'schematic' : mode);
  drawPopulations(ctx, populations, maximumRadius, colors);
  ctx.save();
  ctx.globalCompositeOperation = 'soft-light';
  ctx.globalAlpha = mode === 'polished' ? 0.35 : 0.52;
  ctx.drawImage(polishTexture(), 0, 0, sectionWidth, sectionHeight);
  ctx.restore();
  return message;
}
