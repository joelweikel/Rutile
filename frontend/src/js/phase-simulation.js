// Results belong to one immutable job request, never to an optimization search.
export function initPhaseSimulation(root, readRequest, validate) {
  const $ = id => root.querySelector(`#${id}`);
  let active = null, result = null, completedRequest = null, running = false;
  const escape = value => String(value).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const format = value => Number(value).toLocaleString(undefined, {maximumSignificantDigits: 6});
  const message = text => { $('phase-status').textContent = text; };
  const delay = () => new Promise(resolve => setTimeout(resolve, 700));
  async function api(url, options) {
    const response = await fetch(url, options), value = await response.json();
    if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : 'Check the simulation inputs and source.');
    return value;
  }
  function table(state) {
    return `<div class="phase-table-wrap"><table class="phase-table"><caption>${format(state.temperature_k)} K · phase amounts in mol% · phase compositions in at%</caption><thead><tr><th scope="col">Phase model</th><th scope="col">Amount (mol%)</th><th scope="col">Composition (at%)</th></tr></thead><tbody>${state.phases.map(p => `<tr><th scope="row">${escape(p.label)}${p.linked_disordered_phase ? `<span class="fine"> · includes ${escape(p.linked_disordered_phase)} disordered states</span>` : ''}</th><td>${format(100*p.fraction)}</td><td>${Object.entries(p.composition).map(([element, x]) => `${escape(element)} ${format(100*x)}`).join(' · ')}</td></tr>`).join('')}</tbody></table></div>`;
  }
  function render(value) {
    const transport = value.kawin;
    $('phase-result').innerHTML = `<h3 tabindex="-1">Phases after equilibrium cooling</h3>${table(value.final)}${propertyMarkup(value.properties)}
      <details><summary>Initial annealed state and melt</summary><h4>Initial equilibrium</h4>${table(value.initial)}<h4>Fully mixed melt</h4>${table(value.melt)}</details>
      <details><summary>Cooling path (${value.states.length - 1} equilibrium states)</summary>${value.states.slice(1).map(state => table(state)).join('')}</details>
      <details><summary>Kawin diffusion information</summary>${transport.state === 'completed' ? `<p>${escape(transport.phase)} · ${format(transport.temperature_k)} K</p><ul>${Object.entries(transport.tracer_diffusivity_m2_s).map(([element, d]) => `<li>${escape(element)}: ${Number(d).toExponential(4)} m²/s</li>`).join('')}</ul><p class="fine">${escape(transport.role)}</p>` : `<p class="fine">Unavailable: ${escape(transport.reason)}</p>`}</details>
      <details><summary>Assumptions & sources</summary><ul>${value.assumptions.map(note => `<li>${escape(note)}</li>`).join('')}</ul><p class="fine">${escape(value.provenance.source_name)} · SHA-256 ${escape(value.provenance.source_sha256)}</p><p class="fine">pycalphad ${escape(value.provenance.versions.pycalphad)} · Kawin ${escape(value.provenance.versions.kawin)}</p><p class="fine">Full settings, source transformations, and solver warnings are included in the JSON export.</p></details>`;
    $('phase-result').hidden = false;
    $('phase-export').hidden = false;
    $('phase-result').querySelector('h3').focus({preventScroll: true});
  }
  function propertyMarkup(properties) {
    const density = properties?.density, modulus = properties?.modulus;
    const screening = properties?.screening;
    const shownDensity = density?.state === 'estimated' ? density : screening?.density;
    const shownModulus = modulus?.state === 'estimated' ? modulus : screening?.modulus;
    const densityAvailable = ['estimated', 'screening'].includes(shownDensity?.state);
    const modulusAvailable = ['estimated', 'screening'].includes(shownModulus?.state);
    const covered = value => `${format(100 * (value || 0))}%`;
    return `<section class="property-estimates" aria-label="Density and modulus estimates"><h3>Property estimates</h3><div class="property-estimate-grid"><article><h4>Density</h4><p class="property-value" id="density-estimate">${densityAvailable ? `${format(shownDensity.value_g_cm3)} <span>g/cm³</span>` : 'Unavailable'}</p><p class="fine">${shownDensity?.state === 'screening' ? `Screening: ${escape(shownDensity.method)}` : densityAvailable ? escape(density.source || 'Phase-reference estimate') : escape(shownDensity?.reason || density?.reason || '')}</p></article><article><h4>Young’s modulus</h4><p class="property-value" id="modulus-estimate">${modulusAvailable ? `${format(shownModulus.young_modulus_gpa)} <span>GPa</span>` : 'Unavailable'}</p><p class="fine">${shownModulus?.state === 'screening' ? `Screening: ${escape(shownModulus.method)}` : modulusAvailable ? 'Phase-reference estimate' : escape(shownModulus?.reason || modulus?.reason || '')}</p></article></div>
      <p class="fine">${properties?.reason ? escape(properties.reason) : properties?.physical_density?.state === 'loaded' ? 'Local MatCalc density parameters where supported; optional Materials Project references for remaining coverage. Fully dense estimates.' : 'Materials Project computed references · provisional composition/structure matching · fully dense, isotropic estimate.'}</p>
      ${properties?.phases ? `<details><summary>Property coverage & references</summary><p class="fine">Phase property coverage: density ${covered(properties.density_coverage_mole_fraction)} · elasticity coverage ${covered(properties.elasticity_coverage_mole_fraction)} of molar phase amounts.</p>${density?.reason ? `<p class="fine">${escape(density.reason)}</p>` : ''}${modulus?.reason ? `<p class="fine">${escape(modulus.reason)}</p>` : ''}${modulus?.state === 'estimated' ? `<p class="fine">Reuss–Voigt Young’s modulus range: ${format(modulus.reuss_young_gpa)}–${format(modulus.voigt_young_gpa)} GPa.</p>` : ''}<ul>${properties.phases.map(phase => `<li><strong>${escape(phase.label)}</strong>: ${phase.density_model?.state === 'estimated' ? `MatCalc DP density ${format(phase.density_model.value_g_cm3)} g/cm³ at ${format(phase.density_model.temperature_k)} K · ${escape(phase.density_model.mapping.mapping)}. ` : phase.density_model?.reason ? `Local density unavailable: ${escape(phase.density_model.reason)}. ` : ''}${phase.reference ? `<a href="${escape(phase.reference.url)}" target="_blank" rel="noopener noreferrer">${escape(phase.reference.material_id)}</a> · ${escape(phase.reference.formula)} · ${escape(phase.reference.space_group.symbol)}${phase.reference.disordered_reference_surrogate ? ' · disordered-structure surrogate' : ''}` : escape(`${phase.density_model?.state === 'estimated' ? 'Materials Project reference lookup: ' : ''}${phase.reason || 'No supported reference'}`)}${phase.elasticity_reason ? `<p class="fine">${escape(phase.elasticity_reason)}</p>` : ''}</li>`).join('')}</ul>${screening ? `<h4>Screening references</h4><ul>${screening.references.map(ref => `<li>${escape(ref.element)}: <a href="${escape(ref.url)}" target="_blank" rel="noopener noreferrer">${escape(ref.material_id)}</a> · elemental density ${format(ref.density_g_cm3)} g/cm³</li>`).join('')}${screening.modulus.reference ? `<li>Host modulus: <a href="${escape(screening.modulus.reference.url)}" target="_blank" rel="noopener noreferrer">${escape(screening.modulus.reference.material_id)}</a></li>` : ''}</ul><ul>${screening.assumptions.map(note => `<li>${escape(note)}</li>`).join('')}</ul>` : ''}<p class="fine">${escape(properties.method)}</p><ul>${properties.assumptions.map(note => `<li>${escape(note)}</li>`).join('')}</ul>${properties.physical_density ? `<h4>Local physical database</h4><p class="fine">${properties.physical_density.state === 'loaded' ? `Source SHA-256 ${escape(properties.physical_density.source_sha256)}` : escape(properties.physical_density.reason)}</p>${properties.physical_density.limitations ? `<ul>${properties.physical_density.limitations.map(note => `<li>${escape(note)}</li>`).join('')}</ul>` : ''}` : ''}</details>` : ''}</section>`;
  }
  $('phase-run').addEventListener('click', async () => {
    if (running || !validate()) return;
    running = true; result = null;
    const request = readRequest();
    completedRequest = JSON.stringify(request);
    $('phase-run').disabled = true; $('phase-cancel').hidden = false;
    $('phase-cancel').disabled = true; $('phase-status').classList.remove('error');
    $('phase-export').hidden = true; $('phase-result').hidden = true;
    $('phase-progress').hidden = false; $('phase-progress').removeAttribute('value');
    message('Starting equilibrium calculation…');
    try {
      const job = await api('/api/processing', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(request)});
      active = job.id;
      $('phase-cancel').disabled = false;
      while (active) {
        const status = await api(`/api/jobs/${active}`);
        message(status.message || (status.state === 'running' ? 'Calculating phases…' : status.state));
        if (status.percent != null) $('phase-progress').value = status.percent / 100;
        else $('phase-progress').removeAttribute('value');
        if (status.state === 'failed') throw new Error(status.error || 'Calculation failed.');
        if (status.state === 'cancelled') { message('Calculation cancelled.'); break; }
        if (status.state === 'completed') {
          result = await api(`/api/jobs/${active}/result`);
          render(result);
          message(completedRequest === JSON.stringify(readRequest()) ? 'Equilibrium calculation complete.' : 'Setup changed. Results describe the submitted settings; run again to update.');
          break;
        }
        await delay();
      }
    } catch (error) { $('phase-status').classList.add('error'); message(error.message); }
    finally {
      active = null; running = false;
      $('phase-run').disabled = false; $('phase-cancel').hidden = true; $('phase-progress').hidden = true;
    }
  });
  $('phase-cancel').addEventListener('click', async () => {
    if (!active) return;
    try { await api(`/api/jobs/${active}`, {method: 'DELETE'}); }
    catch (error) { message(error.message); }
  });
  $('phase-export').addEventListener('click', () => {
    if (!result) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], {type: 'application/json'}));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'rutile-arc-melting.json'; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  function changed() {
    if (result && completedRequest !== JSON.stringify(readRequest())) message('Setup changed. Results describe the submitted settings; run again to update.');
  }
  root.addEventListener('input', changed); root.addEventListener('change', changed);
  return {changed};
}
