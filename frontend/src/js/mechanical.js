import {initStrength} from './strength.js';

const $ = id => document.getElementById(id);
const number = (value, digits = 2) => Number.isFinite(value)
  ? value.toLocaleString(undefined, {maximumFractionDigits: digits}) : 'Unavailable';
const withUnit = (value, unit) => Number.isFinite(value) ? `${number(value)} ${unit}` : 'Unavailable';

async function api(path, options) {
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail :
    payload.detail?.map?.(entry => entry.msg).join(' ') || 'Check the tensile test inputs.');
  return payload;
}

function createPlot(canvas, readout) {
  const ctx = canvas.getContext('2d');
  let result, selected, area, displayX;
  const percent = value => number(value * 100, 3);

  function draw() {
    const width = canvas.clientWidth, height = canvas.clientHeight;
    if (!result || !width || !height || !ctx) return;
    const ratio = window.devicePixelRatio || 1;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    ctx.setTransform(canvas.width / width, 0, 0, canvas.height / height, 0, 0);
    const {stress_mpa: y} = result.trace;
    const x = displayX;
    const fit = result.fit?.engineering_curve;
    const xMin = Math.min(0, ...x), xMax = Math.max(...x);
    const yMin = Math.min(0, ...y), yMax = Math.max(...y, ...(fit?.stress_mpa || [])) * 1.04;
    const left = 59, right = width - 15, top = 18, bottom = height - 41;
    if (right <= left) return;
    const sx = v => left + (v - xMin) / (xMax - xMin) * (right - left);
    const sy = v => bottom - (v - yMin) / (yMax - yMin) * (bottom - top);
    area = {left, right, xMin, xMax};
    ctx.font = '11px system-ui, sans-serif';
    ctx.lineWidth = 1;
    ctx.strokeStyle = '#ffffff24';
    ctx.fillStyle = '#c3cbd8';
    for (let i = 0; i <= 4; i++) {
      const strain = xMin + i * (xMax - xMin) / 4, stress = yMin + i * (yMax - yMin) / 4;
      ctx.beginPath();
      ctx.moveTo(sx(strain), top);
      ctx.lineTo(sx(strain), bottom);
      ctx.moveTo(left, sy(stress));
      ctx.lineTo(right, sy(stress));
      ctx.stroke();
      ctx.textAlign = 'center';
      ctx.fillText(number(strain * 100, 1), sx(strain), bottom + 16);
      ctx.textAlign = 'right';
      ctx.fillText(number(stress, 0), left - 6, sy(stress) + 4);
    }
    ctx.textAlign = 'center';
    ctx.fillText('Engineering strain (%)', (left + right) / 2, height - 6);
    ctx.save();
    ctx.translate(13, (top + bottom) / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText('Engineering stress (MPa)', 0, 0);
    ctx.restore();

    function line(xs, ys, color, dashed = false) {
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.setLineDash(dashed ? [5, 4] : []);
      ctx.beginPath();
      xs.forEach((value, i) => i ? ctx.lineTo(sx(value), sy(ys[i])) : ctx.moveTo(sx(value), sy(ys[i])));
      ctx.stroke();
      ctx.setLineDash([]);
    }

    function mark(strain, stress, color, radius) {
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(sx(strain), sy(stress), radius, 0, 2 * Math.PI);
      ctx.fill();
    }
    ctx.save();
    ctx.beginPath();
    ctx.rect(left - 1, top - 1, right - left + 2, bottom - top + 2);
    ctx.clip();
    line(x, y, '#86cdfd');
    if (fit) line(fit.strain, fit.stress_mpa, '#ffc483', true);
    if (Number.isFinite(result.derived.proof_engineering_strain))
      mark(result.derived.proof_engineering_strain, result.derived.proof_stress_0_2_mpa, '#86cdfd', 3);
    if (selected !== undefined) mark(x[selected], y[selected], '#fff', 4);
    ctx.restore();
  }

  function inspect(index) {
    selected = Math.min(Math.max(index, 0), displayX.length - 1);
    readout.textContent = `${percent(displayX[selected])}% strain · ${number(result.trace.stress_mpa[selected])} MPa · reading ${selected + 1} of ${displayX.length}`;
    draw();
  }

  function pick(event) {
    if (!area || !result) return;
    const bounds = canvas.getBoundingClientRect();
    const {left, right, xMin, xMax} = area;
    const target = xMin + ((event.clientX - bounds.left - left) / (right - left)) * (xMax - xMin);
    let nearest = 0;
    for (let i = 1; i < displayX.length; i++)
      if (Math.abs(displayX[i] - target) < Math.abs(displayX[nearest] - target)) nearest = i;
    inspect(nearest);
  }
  canvas.addEventListener('pointermove', event => { if (event.pointerType !== 'touch') pick(event); });
  canvas.addEventListener('click', pick);
  canvas.addEventListener('keydown', event => {
    if (!result || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const current = selected ?? result.measured.peak_index;
    inspect(event.key === 'Home' ? 0 : event.key === 'End' ? displayX.length - 1 :
      current + (event.key === 'ArrowRight' ? 1 : -1) * (event.shiftKey ? 10 : 1));
  });
  new ResizeObserver(draw).observe(canvas);
  return value => {
    result = value;
    area = undefined;
    displayX = value.trace.strain.map(strain => strain - value.trace.strain_zero);
    inspect(value.measured.peak_index);
  };
}

export function initMechanical() {
  const loadStrength = initStrength(api);
  const form = $('tensile-form'), source = $('tensile-source'), results = $('tensile-results');
  const upload = $('tensile-upload'), cancelButton = $('tensile-cancel'), runButton = $('tensile-run');
  const status = $('tensile-status');
  const plot = createPlot($('tensile-plot'), $('tensile-point'));
  let references = new Map(), pendingReferences, result, job, running = false, cancelRequested = false;

  function message(text, error = false) {
    status.textContent = text;
    status.classList.toggle('error', error);
  }

  function syncSource() {
    const reference = references.get(source.value);
    upload.hidden = Boolean(reference);
    for (const control of form.elements) {
      if (control !== cancelButton) control.disabled = running || (upload.hidden && upload.contains(control));
    }
    $('tensile-reference').hidden = !reference;
    $('tensile-reference').textContent = reference?.condition || '';
  }

  async function loadReferences() {
    loadStrength();
    if (pendingReferences) return pendingReferences;
    pendingReferences = api('/api/mechanical/references').then(data => {
      const previous = source.value;
      references = new Map(data.references.map(item => [item.id, item]));
      source.replaceChildren(new Option('Upload a trace', ''), ...data.references.map(item => new Option(item.label, item.id)));
      source.value = references.has(previous) ? previous : '';
      syncSource();
    }).catch(() => {
      if (!running) message('Local examples could not be loaded. You can still upload a trace.');
    }).finally(() => { pendingReferences = null; });
    return pendingReferences;
  }

  function setRunning(value) {
    running = value;
    cancelButton.hidden = !value;
    cancelButton.disabled = false;
    syncSource();
  }

  function render(value) {
    const {settings, measured, derived, fit, provenance} = value;
    $('tensile-result-heading').textContent = settings.material;
    $('tensile-result-condition').textContent = [settings.condition,
      Number.isFinite(settings.temperature_c) ? `${number(settings.temperature_c)} °C` : '',
      Number.isFinite(settings.strain_rate_s) ? `${settings.strain_rate_s} s⁻¹` : ''].filter(Boolean).join(' · ');
    const metrics = [
      ['0.2% proof stress', withUnit(derived.proof_stress_0_2_mpa, 'MPa'), 'From test trace'],
      [measured.peak_confirmed ? 'Test UTS' : 'Recorded peak', withUnit(measured.peak_engineering_stress_mpa, 'MPa'), 'Test trace'],
      ['Young’s modulus', withUnit(derived.young_modulus_gpa, 'GPa'), derived.young_modulus_source === 'supplied' ? 'Supplied' : 'Elastic fit'],
    ];
    if (Number.isFinite(derived.poisson_ratio)) metrics.push(['Poisson’s ratio', number(derived.poisson_ratio, 4), 'Isotropic estimate']);
    if (Number.isFinite(fit?.fitted_uts_mpa)) metrics.push(['Fitted UTS', withUnit(fit.fitted_uts_mpa, 'MPa'), 'Voce fit']);
    if (Number.isFinite(fit?.fitted_uniform_elongation_fraction)) metrics.push(['Fitted uniform elongation',
      withUnit(100 * fit.fitted_uniform_elongation_fraction, '%'), 'Voce peak']);
    if (Number.isFinite(measured.elongation_after_fracture_fraction)) metrics.push(['Elongation after fracture',
      withUnit(100 * measured.elongation_after_fracture_fraction, '%'), 'Reassembled gauge lengths']);
    metrics.push(['Vickers hardness', withUnit(fit?.estimated_vickers_hv, 'HV'),
      Number.isFinite(fit?.estimated_vickers_hv) ? 'Flow-stress estimate' : 'Needs fit coverage at 8% plastic strain']);
    $('tensile-metrics').replaceChildren(...metrics.map(([label, reading, note]) => {
      const card = document.createElement('div'), term = document.createElement('dt'), desc = document.createElement('dd');
      const detail = document.createElement('small');
      term.textContent = label;
      desc.textContent = reading;
      detail.textContent = note;
      desc.append(detail);
      card.append(term, desc);
      return card;
    }));
    $('tensile-fit-key').hidden = !fit;
    $('tensile-warnings').hidden = !value.warnings.length;
    $('tensile-warnings').replaceChildren(...value.warnings.map(warning => {
      const row = document.createElement('li');
      row.textContent = warning;
      return row;
    }));
    const details = $('tensile-details');
    details.replaceChildren();
    function detail(text) {
      const p = document.createElement('p');
      p.className = 'fine';
      p.textContent = text;
      details.append(p);
      return p;
    }
    if (fit) {
      const [low, high] = fit.plastic_strain_range;
      detail(`Voce fit · RMSE ${number(fit.rmse_mpa)} MPa · ${number(low * 100)}–${number(high * 100)}% true plastic strain`);
      detail(`Initial flow stress ${number(fit.initial_flow_stress_mpa)} MPa · saturation increment ${number(fit.saturation_increment_mpa)} MPa · characteristic strain ${number(100 * fit.characteristic_plastic_strain)}%`);
      if (fit.fitted_uts_mpa === null) detail('The fit has no engineering stress peak within the measured fit range.');
    }
    detail(provenance.source_name);
    if (provenance.source_url) {
      const link = document.createElement('a');
      link.href = provenance.source_url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = 'Original dataset';
      details.append(link);
    }
    detail(`Source SHA-256 ${provenance.source_sha256}`);
    value.assumptions.forEach(detail);
    results.hidden = false;
    plot(value);
    if (!results.closest('.screen').hidden) {
      $('tensile-result-heading').focus({preventScroll: true});
      if (matchMedia('(max-width: 850px)').matches) results.scrollIntoView({block: 'start'});
    }
  }

  function fileContent(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result.split(',')[1]);
      reader.onerror = () => reject(new Error('Could not read the tensile file.'));
      reader.readAsDataURL(file);
    });
  }

  form.addEventListener('invalid', event => {
    const details = event.target.closest('details');
    if (details) details.open = true;
  }, true);
  source.addEventListener('change', syncSource);
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (running) return;
    const optional = id => $(id).value === '' ? null : Number($(id).value);
    const reference = source.value;
    const body = {young_gpa: optional('tensile-young'), shear_gpa: optional('tensile-shear'),
      initial_gauge_length_mm: optional('tensile-gauge-initial'), final_gauge_length_mm: optional('tensile-gauge-final')};
    const file = $('tensile-file').files[0];
    if (!reference && (!file || file.size > 2 * 1024 * 1024)) {
      message('Choose a tensile file no larger than 2 MB.', true);
      return;
    }
    if (reference) body.reference_id = reference;
    else Object.assign(body, {filename: file.name, material: $('tensile-material').value.trim(),
      condition: $('tensile-condition').value.trim(), strain_unit: $('tensile-unit').value,
      temperature_c: optional('tensile-temperature'), strain_rate_s: optional('tensile-rate')});
    setRunning(true);
    results.hidden = true;
    result = null;
    cancelRequested = false;
    message('Preparing tensile analysis…');
    try {
      if (!reference) body.content = await fileContent(file);
      if (cancelRequested) { message('Analysis cancelled.'); return; }
      job = (await api('/api/mechanical', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body)})).id;
      if (cancelRequested) await api(`/api/jobs/${job}`, {method: 'DELETE'});
      let state = await api(`/api/jobs/${job}`);
      while (state.state === 'running') {
        if (!cancelRequested) message(state.message || 'Analyzing the tensile trace…');
        await new Promise(resolve => setTimeout(resolve, 400));
        state = await api(`/api/jobs/${job}`);
      }
      if (state.state === 'completed') {
        result = await api(`/api/jobs/${job}/result`);
        render(result);
        message('');
      } else {
        message(state.state === 'cancelled' ? 'Analysis cancelled.' : state.error || 'Tensile analysis failed.',
          state.state !== 'cancelled');
      }
    } catch (error) {
      message(error.message, true);
    } finally {
      job = null;
      setRunning(false);
    }
  });
  cancelButton.addEventListener('click', async () => {
    cancelRequested = true;
    cancelButton.disabled = true;
    message('Requesting cancellation…');
    if (job) {
      try { await api(`/api/jobs/${job}`, {method: 'DELETE'}); }
      catch (error) { cancelButton.disabled = false; message(error.message, true); }
    }
  });
  $('tensile-export').addEventListener('click', () => {
    if (!result) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], {type: 'application/json'}));
    const link = document.createElement('a');
    link.href = url;
    link.download = `rutile-tensile-${result.settings.material.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '') || 'trace'}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  return {loadReferences};
}
