import {families, materialId} from './alloy-graph.js';
import {phaseDataRequest} from './alloy-phase-data.js';
import {scheduleIssue} from './processing-events.js';

export async function studioApi(path, options) {
  const response = await fetch(path, options);
  const value = await response.json();
  if (!response.ok) {
    const detail = Array.isArray(value.detail) ? value.detail.map(item => `${item.loc.at(-1)}: ${item.msg}`).join(' · ') : value.detail;
    throw new Error(detail || 'The server could not complete the request.');
  }
  return value;
}

export function studioPost(path, body) {
  return studioApi(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
}

export function createStudioRuns(getGraph, changed, report, getSourceCatalog) {
  const results = new Map();
  let activeJob = null, cancelled = false;
  const nodeById = id => getGraph().nodes.find(node => node.id === id);
  const upstream = (node, pin) => nodeById(getGraph().edges.find(edge => edge[2] === node.id && edge[3] === pin)?.[0]);

  function sourceInput(node, role) {
    const {file, preset: choice} = node.settings;
    if (file) return {name: file.name, file};
    const catalog = getSourceCatalog();
    const preset = catalog?.sources.find(item => item.family === choice);
    if (role === 'assessment') {
      if (!families.includes(choice)) return {issue: 'Choose a thermodynamic file.'};
      return {preset: choice, name: preset?.thermodynamic || `MatCalc ${choice} assessment`,
        issue: preset?.available === false ? `${preset.thermodynamic} is unavailable.` : null};
    }
    if (role === 'mobility') {
      if (!families.includes(choice)) return {issue: 'Choose a compatible mobility file.'};
      return {preset: choice, name: preset?.mobility || `MatCalc ${choice} mobility`,
        issue: preset?.mobility_available === false ? `${preset.mobility} is unavailable.` : null};
    }
    if (choice !== 'configured') return {issue: 'Choose a physical data file.'};
    return {preset: choice, name: catalog?.physical?.name || 'Configured physical data',
      issue: catalog?.physical?.available === false ? `${catalog.physical.name} is unavailable.` : null};
  }

  function requiredSource(node, role) {
    const input = sourceInput(node, role);
    if (input.issue) throw new Error(input.issue);
    return input;
  }

  function equilibriumRequest(node) {
    const alloy = upstream(node, 'composition')?.settings;
    const schedule = upstream(node, 'schedule')?.settings;
    const source = upstream(node, 'assessment');
    if (!alloy) throw new Error('Connect Composition.');
    if (!source) throw new Error('Connect a thermodynamic assessment.');
    if (!schedule) throw new Error('Connect Processing Schedule.');
    const assessment = requiredSource(source, 'assessment');
    const family = alloy.base;
    if (assessment.preset && family !== assessment.preset) throw new Error('The composition base element must match the assessment family.');
    if (!families.includes(family)) throw new Error('Choose a supported base element.');
    const element = alloy.element.trim().toUpperCase();
    if (!/^[A-Z]{1,2}$/.test(element) || element === alloy.base || !(alloy.amount > 0 && alloy.amount < 100)) {
      throw new Error('Enter a distinct alloying element and an addition between 0 and 100%.');
    }
    const issue = scheduleIssue(schedule);
    if (issue) throw new Error(issue);
    return {
      family, database_id: assessment.file?.id ?? null, composition_mode: 'fixed', composition_basis: alloy.basis,
      additions: [{element, minimum: alloy.amount, maximum: alloy.amount}], route: schedule.route,
      initial_temperature_k: schedule.initial,
      ...(schedule.route === 'arc_melting' ? {melt_temperature_k: schedule.melt, final_temperature_k: schedule.final} : {}),
      pressure_pa: schedule.pressure,
      ...(schedule.route === 'arc_melting' ? {cooling_points: schedule.points} : {}),
      ...(schedule.events.length ? {events: schedule.events} : {}),
      include_reference_properties: false, allow_screening_estimates: false, use_physical_density: false, source_only: true,
    };
  }

  function jobInputs(node) {
    if (node.type === 'equilibrium') return equilibriumRequest(node);
    const parent = upstream(node, 'phase');
    if (node.type === 'phaseAssignment') {
      if (!parent) throw new Error('Connect a Phase Set from equilibrium.');
      const saved = current(parent);
      const source = upstream(node, 'physical');
      const input = source && requiredSource(source, 'physical');
      const choices = {};
      for (const phase of saved?.result.phase_set?.phases || []) {
        const key = phase.instance_id;
        const material_id = node.settings.materialIds[key] || null;
        const manual = upstream(node, key);
        try {
          if (material_id && !materialId.test(material_id)) throw new Error('Enter a valid Materials Project ID.');
          const record = manual && phaseDataRequest(manual.settings);
          if (material_id || record) choices[key] = {material_id: material_id || record?.material_id || null, data: record?.data || null};
        } catch (error) { throw new Error(`${phase.label} · ${error.message}`); }
      }
      return {equilibrium_job: saved?.job ?? null, choices, include_reference_properties: node.settings.references,
        companion_id: input?.file?.id ?? null, companion_preset: input?.preset ?? null, use_physical_density: Boolean(source)};
    }
    if (!parent) throw new Error('Connect a Final Phase Set from Phase Assignment.');
    const equilibrium = upstream(parent, 'phase');
    if (!equilibrium) throw new Error('Connect a Phase Set to Phase Assignment.');
    const phaseSource = upstream(equilibrium, 'assessment');
    const role = node.type === 'density' ? 'physical' : 'mobility';
    const source = upstream(node, role);
    if (node.type === 'tracer' && !source) throw new Error('Connect Mobility Data or a Mobility File.');
    const input = source && requiredSource(source, role);
    if (role === 'mobility' && input?.preset && phaseSource?.settings.preset && input.preset !== phaseSource.settings.preset) {
      throw new Error('Use the assessment’s named mobility companion or connect an explicit mobility file.');
    }
    const saved = current(parent);
    return {equilibrium_job: saved?.result.equilibrium_job ?? null, assignment_job: saved?.job ?? null, operation: node.type,
      companion_id: input?.file?.id ?? null, companion_preset: input?.preset ?? null, use_physical_density: node.type === 'density',
      allow_parent_density: node.type === 'density' && node.settings.parentDensity,
      include_reference_properties: node.type === 'density' && node.settings.references};
  }

  function signature(node) {
    return JSON.stringify(jobInputs(node));
  }

  function inputIssue(node) {
    try {
      if (node.type === 'phaseData') phaseDataRequest(node.settings);
      else {
        const parent = upstream(node, 'phase');
        if (node.type === 'viewer' && !parent) return 'Connect a Final Phase Set from Phase Assignment.';
        if (node.type !== 'viewer') jobInputs(node);
        if (parent) return inputIssue(parent);
      }
      return null;
    } catch (error) { return error.message; }
  }

  function current(node) {
    const saved = results.get(node.id);
    if (!saved) return null;
    if (node.type === 'equilibrium' && saved.result.phase_set?.phases.some(
      phase => phase.linked_disordered_phase && !phase.substitutional_disorder)) return null;
    try { return saved.key === signature(node) ? saved : null; }
    catch { return null; }
  }

  async function perform(node, force = false) {
    if (cancelled) return;
    if (node.type !== 'equilibrium') {
      // Validate branch connections before spending time on its prerequisite.
      jobInputs(node);
      const parent = upstream(node, 'phase');
      if (!current(parent)) await perform(parent);
    }
    if (cancelled || (!force && current(node))) return;
    const input = jobInputs(node);
    const key = JSON.stringify(input);
    const path = node.type === 'equilibrium' ? '/api/workflow/equilibrium' :
      node.type === 'phaseAssignment' ? '/api/workflow/phase-assignment' : '/api/workflow/branch';
    report(node, 'Submitting…');
    const job = await studioPost(path, input);
    activeJob = job.id;
    try {
      if (cancelled) await studioApi(`/api/jobs/${activeJob}`, {method: 'DELETE'});
      while (true) {
        const status = await studioApi(`/api/jobs/${activeJob}`);
        if (status.state === 'cancelled') {
          cancelled = true;
          report(node, 'Canceled');
          return;
        }
        if (status.state === 'failed') throw new Error(status.error || 'Calculation failed.');
        if (status.state === 'completed') {
          const result = await studioApi(`/api/jobs/${activeJob}/result`);
          results.set(node.id, {job: activeJob, key, result});
          changed();
          let message = 'Complete';
          if (node.type === 'phaseAssignment') {
            const unresolved = result.phase_set.phases.filter(phase => !phase.reference && phase.phase_data?.state !== 'applicable');
            if (unresolved.length) message = `Complete · ${unresolved.length} phases need reference data`;
          } else if (node.type === 'density' && result.properties?.density?.state !== 'estimated') {
            message = 'Complete · phase volume data missing';
          } else if (node.type === 'tracer' && result.kawin?.state === 'unavailable') {
            message = 'Complete · tracer data unavailable';
          }
          report(node, message, 100);
          return;
        }
        report(node, status.message || 'Preparing calculation…', status.percent);
        await new Promise(resolve => setTimeout(resolve, 320));
      }
    } finally {
      activeJob = null;
    }
  }

  return {
    results, current, upstream, inputIssue, sourceInput,
    async run(targets, force) {
      cancelled = false;
      for (const node of targets) {
        if (cancelled) break;
        try { await perform(node, force); }
        catch (error) { report(node, error.message, undefined, true); }
      }
    },
    async cancel() {
      cancelled = true;
      if (activeJob) await studioApi(`/api/jobs/${activeJob}`, {method: 'DELETE'});
    },
    async restore(entries) {
      for (const [id, saved] of entries) {
        if (!nodeById(id) || typeof saved?.job !== 'string' || typeof saved.key !== 'string' ||
            !/^[a-f0-9-]{36}$/.test(saved.job)) continue;
        try {
          const result = await studioApi(`/api/jobs/${saved.job}/result`);
          results.set(id, {...saved, result});
        } catch {
          // Graphs remain editable when an earlier run was removed from disk.
        }
      }
    },
  };
}
