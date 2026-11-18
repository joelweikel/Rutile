import {materialId} from './alloy-graph.js';
import {researchTargets} from './alloy-reference-research.js';

export function phaseProperties(phase, escape, format) {
  if (!phase) return '';
  const density = phase.density_model?.state === 'estimated' ? phase.density_model : null;
  const elasticity = phase.elasticity;
  const manual = phase.phase_data;
  const reference = phase.reference;
  const evidence = Object.entries(manual?.record?.research || {}).map(([property, item]) =>
    `<li>${escape(property === 'density' ? 'Density' : 'Elasticity')} ·
      <a href="${escape(item.url)}" target="_blank" rel="noopener noreferrer">${escape(item.source)}</a>
      · ${escape(item.locator)}${item.extrapolated ? ' · Extrapolated' : ''}</li>`).join('');
  const id = reference?.material_id || phase.resolved_material_id || phase.requested_material_id || phase.translation?.candidate?.mp_id;
  const link = id && materialId.test(id) ? `<a href="https://materialsproject.org/materials/${id}" target="_blank" rel="noopener noreferrer">${id}</a>` : '';
  const details = [
    density && `<li>Density · ${format(density.value_g_cm3)} g/cm³ · ${escape(density.source || 'MatCalc DP')}</li>`,
    reference?.density_g_cm3 && `<li>Crystal reference density · ${format(reference.density_g_cm3)} g/cm³</li>`,
    elasticity && `<li>Elasticity · E ${format(elasticity.young_modulus_gpa)} GPa · K ${format(elasticity.bulk_modulus_gpa)} GPa · G ${format(elasticity.shear_modulus_gpa)} GPa</li>`,
    manual?.state === 'applicable' && manual.record.bulk_modulus_gpa && !manual.record.shear_modulus_gpa &&
      `<li>Attached bulk modulus · ${format(manual.record.bulk_modulus_gpa)} GPa</li>`,
    manual?.state === 'applicable' && manual.record.shear_modulus_gpa && !manual.record.bulk_modulus_gpa &&
      `<li>Attached shear modulus · ${format(manual.record.shear_modulus_gpa)} GPa</li>`,
    ...Object.entries(phase.attached_properties || {}).map(([name, property]) =>
      `<li>${escape(name)} · ${format(property.value)} ${escape(property.unit)}</li>`),
  ].filter(Boolean);
  return `${link ? `<p>${link} · ${escape(reference ? phase.matching_status : 'Identity awaiting applicable data')}</p>` : ''}
    ${details.length ? `<ul>${details.join('')}</ul>` : ''}
    ${manual ? `<p>${escape(manual.record.source)} · ${escape(manual.record.origin)}${manual.reason ? ` · ${escape(manual.reason)}` : ''}</p>` : ''}
    ${evidence ? `<ul>${evidence}</ul>` : ''}
    ${phase.reason && !reference ? `<p class="fine">${escape(phase.reason)}</p>` : ''}
    ${phase.elasticity_reason && !elasticity ? `<p class="fine">${escape(phase.elasticity_reason)}</p>` : ''}`;
}

export function phaseAssignmentMarkup(node, rawSet, assignedSet, upstream, escape, format) {
  if (!rawSet) return '<p class="fine">Run equilibrium to list phases.</p>';
  const assigned = new Map((assignedSet?.phases || []).map(phase => [phase.instance_id, phase]));
  return `<p class="studio-condition"><span>${format(rawSet.temperature_k)} K</span><span>${format(rawSet.pressure_pa)} Pa</span></p>
    <div class="studio-assignment-rows">${rawSet.phases.map(phase => {
      const key = phase.instance_id;
      const result = assigned.get(key);
      const record = upstream(node, key);
      const id = node.settings.materialIds[key] || '';
      return `<section class="studio-assignment-row">
        <h4>${escape(phase.label)} <span>${format(100 * phase.fraction)} mol%</span></h4>
        <p class="fine">${Object.entries(phase.composition).map(([element, fraction]) =>
          `${escape(element)} ${format(100 * fraction)} at%`).join(' · ')}</p>
        <label>Materials Project ID<input data-mp-phase="${key}" maxlength="24" spellcheck="false" value="${escape(id)}"
          placeholder="${escape(result?.reference?.material_id || result?.requested_material_id || record?.settings.materialId || 'Auto or enter mp-…')}"
          ${id && !materialId.test(id) ? 'aria-invalid="true"' : ''}></label>
        <button type="button" class="studio-pin input studio-inspector-pin${record ? ' connected' : ''}"
          data-pin="${key}" data-owner="${node.id}" data-direction="input" data-type="phase-record"
          aria-label="Phase Data input for ${escape(phase.label)}"><i aria-hidden="true"></i>${record ?
            escape(record.settings.name || 'Connected Phase Data') : 'Phase Data'}</button>
        ${record ? `<button type="button" class="secondary" data-select="${record.id}">Edit Phase Data</button>` :
          `<button type="button" class="secondary" data-add-phase-data="${key}">Add phase data</button>`}
        ${result && researchTargets({phases: [result]}).length ?
          `<button type="button" class="secondary" data-research-phase="${key}">Find reference</button>` : ''}
        ${phaseProperties(result, escape, format)}
      </section>`;
    }).join('')}</div>`;
}
