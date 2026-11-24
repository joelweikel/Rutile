import {phaseColorRecord} from './alloy-phase-colors.js';

function swatch(color) {
  const value = /^#[0-9a-f]{6}$/.test(color) ? color : '#838383';
  return `<span class="studio-optical-swatch" style="--phase-color:${value}" aria-hidden="true"></span>`;
}

function lab(row, format) {
  return row.lab.map(value => format(value)).join(' / ');
}

export function opticalResultMarkup(result, esc, format) {
  return `<p class="fine">${esc(result.reference_condition)}</p>
    <table><thead><tr><th>Phase</th><th>Color</th><th>L* / a* / b*</th></tr></thead>
      <tbody>${result.optical_phases.map(row => {
        const color = row.color;
        const modeled = color?.modeled_composition_mole_fraction;
        const modeledComposition = modeled && Object.entries(modeled)
          .map(([element, fraction]) => `${element} ${format(fraction * 100)} at%`).join(' · ');
        const paletteNote = row.palette_reason ? `<br><small>${esc(row.palette_reason)}</small>` : '';
        return `<tr><td>${esc(row.label)}${paletteNote}</td>${color ?
          `<td>${swatch(color.srgb_hex)} ${esc(color.origin)}${modeled ? `<br><small>${esc(color.structure)} · ${esc(modeledComposition)}</small>` : ''}
           </td><td>${lab(color, format)}</td>` :
          `<td colspan="2">${esc(row.reason)}</td>`}</tr>`;
      }).join('')}</tbody></table>`;
}

export function opticalScreenMarkup(rows, esc, format) {
  if (!rows) return '';
  return `<p class="fine">Published calculated spectra · D65 / 2° · ranked by CIELAB chroma</p>
    <table><thead><tr><th>Compound</th><th>Swatch</th><th>C*ab</th></tr></thead>
      <tbody>${rows.map(row => `<tr><td>${esc(row.formula)} · ${esc(row.structure)}</td>
        <td>${swatch(row.srgb_hex)} <code>${esc(row.srgb_hex)}</code></td>
        <td>${format(row.chroma_ab)}</td></tr>`).join('')}</tbody></table>
    <p class="fine"><a href="https://doi.org/10.5281/zenodo.3822037" target="_blank" rel="noopener">Rahm et al. optical dataset</a></p>`;
}

export function spectralMatrixColors(optical, microstructure, sample) {
  if (!optical || !microstructure?.microstructure || !sample?.matrix_composition_mole_fraction ||
      optical.equilibrium_job !== microstructure.equilibrium_job) return {};
  const key = microstructure.microstructure.matrix_phase;
  const actual = sample.matrix_composition_mole_fraction;
  const matches = optical.optical_phases.filter(phase => {
    if (phase.phase !== key || !phase.color) return false;
    const reference = phase.color.composition_mole_fraction;
    const elements = new Set([...Object.keys(actual), ...Object.keys(reference)]);
    return [...elements].every(element => Math.abs((actual[element] ?? 0) - (reference[element] ?? 0)) <= 1e-6);
  });
  return matches.length === 1 ? phaseColorRecord({[key]: matches[0].color.srgb_hex}).colors : {};
}
