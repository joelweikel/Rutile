import {materialId as validMaterialId} from './alloy-graph.js';

const numericFields = {
  temperature_k: 'Temperature (K)', pressure_pa: 'Pressure (Pa)', density_g_cm3: 'Density (g/cm³)',
  bulk_modulus_gpa: 'Bulk modulus (GPa)', shear_modulus_gpa: 'Shear modulus (GPa)',
};

export function phaseDataMarkup(settings, escape) {
  const field = (key, label, type, options = '') =>
    `<label>${label}<input data-field="${key}" type="${type}" value="${escape(settings[key])}" ${options}></label>`;
  const json = (key, label, example, limit) =>
    `<label>${label}<textarea data-field="${key}" rows="3" maxlength="${limit}" spellcheck="false" placeholder='${example}'>${escape(settings[key])}</textarea></label>`;
  return field('name', 'Phase name', 'text', 'maxlength="240"') +
    field('materialId', 'Materials Project ID or link', 'text', 'maxlength="240" spellcheck="false" placeholder="mp-998"') +
    `<details ${!settings.materialId || hasProperties(settings) ? 'open' : ''}><summary>Local phase properties</summary>` +
    field('source', 'Source or citation', 'text', 'maxlength="240"') +
    `<label>Data origin<select data-field="origin">${['sourced', 'measured', 'computed'].map(
      origin => `<option ${settings.origin === origin ? 'selected' : ''}>${origin}</option>`).join('')}</select></label>` +
    `<div class="studio-phase-numbers">${Object.entries(numericFields).map(
      ([key, label]) => field(key, label, 'number', 'step="any" min="0"')).join('')}</div>` +
    json('composition_mole_fraction', 'Composition (atomic fractions)', '{"AL": 0.667, "CU": 0.333}', 2000) +
    json('properties', 'Additional properties (JSON)', '{"thermal_conductivity": {"value": 25, "unit": "W/(m·K)"}}', 10000) + '</details>';
}

function hasProperties(settings) {
  return ['density_g_cm3', 'bulk_modulus_gpa', 'shear_modulus_gpa', 'properties'].some(key => settings[key].trim());
}

function parseMaterialId(value) {
  if (!value.trim()) return null;
  const text = value.trim().toLowerCase();
  const id = /^https:\/\/(?:www\.)?materialsproject\.org\/materials\/([^/?#]+)\/?(?:[?#].*)?$/.exec(text)?.[1] || text;
  if (!validMaterialId.test(id)) throw new Error('Enter a Materials Project ID or materials page link.');
  return id;
}

function object(text, label) {
  let value;
  try { value = JSON.parse(text); } catch { throw new Error(`Enter valid JSON for ${label}.`); }
  if (!value || Array.isArray(value) || typeof value !== 'object') throw new Error(`Enter a JSON object for ${label}.`);
  return value;
}

export const researchProperties = {
  density: ['density_g_cm3'], elasticity: ['bulk_modulus_gpa', 'shear_modulus_gpa'],
};

export function removeEditedResearch(settings, field) {
  if (!settings.research) return;
  if (['temperature_k', 'pressure_pa', 'composition_mole_fraction'].includes(field)) {
    settings.research = '';
    return;
  }
  const property = Object.keys(researchProperties).find(name => researchProperties[name].includes(field));
  if (!property) return;
  const research = object(settings.research, 'research provenance');
  delete research[property];
  settings.research = JSON.stringify(research);
}

export function mergeResearchPhaseData(settings, data) {
  const existing = hasProperties(settings) ? phaseDataRequest(settings).data : null;
  if (existing && (
    Math.abs(existing.temperature_k - data.temperature_k) > .1 ||
    Math.abs(existing.pressure_pa - data.pressure_pa) > 1 ||
    [...new Set([...Object.keys(existing.composition_mole_fraction), ...Object.keys(data.composition_mole_fraction)])].some(
      element => Math.abs((existing.composition_mole_fraction[element] || 0) - (data.composition_mole_fraction[element] || 0)) > 1e-4)
  )) throw new Error(`${data.name} has existing Phase Data at different conditions.`);
  const research = existing?.research || {};
  const entries = Object.entries(data.research);
  for (const [property, provenance] of entries) {
    const fields = researchProperties[property];
    if (research[property]?.proposal_id === provenance.proposal_id &&
        fields.every(field => Number(settings[field]) === data[field])) continue;
    if (fields.some(field => settings[field].trim())) {
      throw new Error(`${data.name} already has a value for ${property}. Review its Phase Data before applying a replacement.`);
    }
    for (const field of fields) settings[field] = String(data[field]);
    research[property] = provenance;
  }
  if (!existing) Object.assign(settings, {
    name: settings.name || data.name, source: data.source, origin: data.origin,
    temperature_k: String(data.temperature_k), pressure_pa: String(data.pressure_pa),
    composition_mole_fraction: JSON.stringify(data.composition_mole_fraction),
  });
  settings.research = JSON.stringify(research);
}

export function phaseDataRequest(settings) {
  const {name, source, origin} = settings;
  const material_id = parseMaterialId(settings.materialId);
  if (material_id && !hasProperties(settings)) return {material_id, data: null};
  if (!name.trim() || !source.trim()) throw new Error('Enter a phase name and source or citation.');
  if (!['sourced', 'measured', 'computed'].includes(origin)) throw new Error('Choose a phase data origin.');
  const values = {};
  for (const [key, label] of Object.entries(numericFields)) {
    if (!settings[key] && key !== 'temperature_k' && key !== 'pressure_pa') continue;
    const value = Number(settings[key]);
    if (!Number.isFinite(value) || value <= 0 || (key === 'temperature_k' && value > 4000) ||
        (key === 'pressure_pa' && value > 1e9)) throw new Error(`Enter a valid ${label.toLowerCase()}.`);
    values[key] = value;
  }
  const composition = object(settings.composition_mole_fraction, 'composition');
  const fractions = Object.entries(composition);
  if (!fractions.length || fractions.length > 20 || fractions.some(([element, value]) =>
    !/^[A-Z]{1,2}$/.test(element) || !Number.isFinite(value) || value < 0 || value > 1) ||
    Math.abs(fractions.reduce((sum, [, value]) => sum + value, 0) - 1) > 1e-5) {
    throw new Error('Use uppercase element symbols and atomic fractions that sum to 1.');
  }
  const properties = settings.properties.trim() ? object(settings.properties, 'additional properties') : {};
  const additional = Object.entries(properties);
  if (additional.length > 32 || additional.some(([name, record]) => !name.trim() || name.length > 240 ||
    !Number.isFinite(record?.value) || typeof record.unit !== 'string' || !record.unit.trim() || record.unit.length > 240 ||
    Object.keys(record).some(key => key !== 'value' && key !== 'unit'))) {
    throw new Error('Enter up to 32 additional properties, each with a numeric value and a unit.');
  }
  if (!values.density_g_cm3 && !values.bulk_modulus_gpa && !values.shear_modulus_gpa && !additional.length) {
    throw new Error('Enter at least one phase property.');
  }
  const research = settings.research?.trim() ? object(settings.research, 'research provenance') : {};
  return {material_id, data: {name: name.trim(), source: source.trim(), origin, composition_mole_fraction: composition,
    ...values, properties, ...(Object.keys(research).length ? {research} : {})}};
}
