export const phaseColorLimit = 64;
export const colorPhaseKey = /^[A-Z][A-Z0-9_]{0,79}$/;
const hexColor = /^#[a-f\d]{6}$/i;
export const appearanceModes = {schematic: 'Schematic', polished: 'Polished reference', etched: 'Etched reference'};
export const polishedReferences = {
  copper: {label: 'Polished pure copper', color: '#f7d1c1', url: 'https://www.spectraldb.com/measurements/00485/'},
  auga2: {label: 'AuGa₂ · bluish-gray', color: '#a5b0ba', url: 'https://link.springer.com/article/10.1007/bf03214961'},
};

export function phaseColorRecord(colors = {}, references = {}) {
  const entries = Object.entries(colors).filter(([phase, color]) => colorPhaseKey.test(phase) &&
    typeof color === 'string' && hexColor.test(color)).slice(0, phaseColorLimit);
  const normalized = Object.fromEntries(entries.map(([phase, color]) => [phase, color.toLowerCase()]));
  const matching = Object.fromEntries(Object.keys(normalized).flatMap(phase => {
    const id = references[phase];
    return Object.hasOwn(polishedReferences, id) && polishedReferences[id].color === normalized[phase] ? [[phase, id]] : [];
  }));
  return {kind: 'phase_colors', schema_version: 1, colors: normalized,
    ...(Object.keys(matching).length ? {references: matching} : {})};
}

export function restorePhaseColorRecord(value) {
  return phaseColorRecord(value?.kind === 'phase_colors' && value.schema_version === 1 &&
    value.colors && typeof value.colors === 'object' && !Array.isArray(value.colors) ? value.colors : {},
  value?.references ?? {});
}

export function appearancePaletteKey(mode) {
  return mode === 'polished' ? 'polishedPalette' : mode === 'etched' ? 'etchedPalette' : 'palette';
}

export function phaseColorsMarkup(settings, suggestions, esc) {
  const mode = settings.appearance;
  const record = settings[appearancePaletteKey(mode)];
  const entries = Object.entries(record.colors);
  return `<div data-phase-color-editor>
    <label>Appearance<select data-field="appearance" aria-label="Appearance">${Object.entries(appearanceModes).map(([key, label]) =>
      `<option value="${key}" ${key === mode ? 'selected' : ''}>${label}</option>`).join('')}</select></label>
    ${mode === 'polished' ? '<p class="fine">Assign approximate reference swatches to identified phases.</p>' : ''}
    ${mode === 'etched' ? `<label>Etchant<input data-field="etchant" maxlength="120" placeholder="Ferric chloride" value="${esc(settings.etchant)}"></label>
      <label>Preparation and imaging conditions<input data-field="etchConditions" maxlength="480"
        placeholder="Sample, exposure, and lighting" value="${esc(settings.etchConditions)}"></label>
      <label>Reference image or source<input data-field="etchSource" maxlength="480" value="${esc(settings.etchSource)}"></label>
      <p class="fine">Enter observed swatches for this preparation.</p>` : ''}
    <div class="studio-phase-colors">${entries.map(([phase, color]) => `
    <div class="studio-phase-color-row">
      <label><span>${esc(phase)}</span><input type="color" value="${esc(color)}" data-phase-color="${esc(phase)}"
        aria-label="Color for ${esc(phase)}"></label>
      <button type="button" class="secondary" data-remove-phase-color="${esc(phase)}"
        aria-label="Remove color for ${esc(phase)}">Remove</button>
    </div>
    ${mode === 'polished' ? `<label>Reference for ${esc(phase)}<select data-polished-reference="${esc(phase)}"
      aria-label="Reference for ${esc(phase)}">
      <option value="">Custom swatch</option>${Object.entries(polishedReferences).map(([id, item]) =>
        `<option value="${id}" ${record.references?.[phase] === id ? 'selected' : ''}>${item.label}</option>`).join('')}
      </select></label>` : ''}`).join('')}</div>
    ${entries.length < phaseColorLimit ? `<form class="studio-phase-color-form" data-phase-color-form>
      <label>Phase key <input name="phase" list="studio-phase-color-keys" maxlength="80" required></label>
      <datalist id="studio-phase-color-keys">${suggestions.map(phase => `<option value="${esc(phase)}"></option>`).join('')}</datalist>
      <button type="submit" class="secondary">Add color</button>
    </form>` : ''}</div>`;
}
