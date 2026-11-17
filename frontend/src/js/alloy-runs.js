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

export function createStudioRuns(getGraph, changed, report) {
  const results = new Map();
  let activeJob = null, cancelled = false;
  const nodeById = id => getGraph().nodes.find(node => node.id === id);
  const upstream = (node, pin) => nodeById(getGraph().edges.find(edge => edge[2] === node.id && edge[3] === pin)?.[0]);

  function sourceFile(node, pin) {
    const fileNode = upstream(node, pin);
    if (fileNode && !fileNode.settings.file) throw new Error(`Choose the ${pin} file connected to MatCalc Sources.`);
    return fileNode?.settings.file;
  }

  function equilibriumRequest(node) {
    const alloy = upstream(node, 'composition')?.settings;
    const schedule = upstream(node, 'schedule')?.settings;
    const source = upstream(node, 'assessment');
    if (!alloy || !schedule || !source) throw new Error('Connect Composition, MatCalc Sources, and Processing Schedule.');
    const family = source.settings.family;
    if (alloy.base !== family) throw new Error('The composition base element must match the MatCalc family.');
    const element = alloy.element.trim().toUpperCase();
    if (!/^[A-Z]{1,2}$/.test(element) || element === alloy.base || !(alloy.amount > 0 && alloy.amount < 100)) {
      throw new Error('Enter a distinct alloying element and an addition between 0 and 100%.');
    }
    return {
      family, database_id: sourceFile(source, 'assessment')?.id ?? null, composition_mode: 'fixed', composition_basis: alloy.basis,
      additions: [{element, minimum: alloy.amount, maximum: alloy.amount}], route: 'arc_melting',
      initial_temperature_k: schedule.initial, melt_temperature_k: schedule.melt, final_temperature_k: schedule.final,
      pressure_pa: schedule.pressure, cooling_points: schedule.points,
      include_reference_properties: false, allow_screening_estimates: false, use_physical_density: true,
    };
  }

  function jobInputs(node) {
    if (node.type === 'equilibrium') return equilibriumRequest(node);
    const equilibrium = upstream(node, 'phase');
    if (!equilibrium) throw new Error('Connect an equilibrium Phase Set.');
    const phaseSource = upstream(equilibrium, 'assessment');
    const role = node.type === 'density' ? 'physical' : 'mobility';
    const source = upstream(node, role);
    if (node.type === 'tracer' && !source) throw new Error('Connect Mobility Data from MatCalc Sources or a Mobility File.');
    if (source?.type === 'sources' && source.id !== phaseSource?.id) {
      throw new Error('Connect the MatCalc Sources node used by the equilibrium calculation, or connect an explicit file.');
    }
    const file = source?.type === 'sources' ? sourceFile(source, role) : source?.settings.file;
    if (source && source.type !== 'sources' && !file) throw new Error(`Choose the connected ${role} file.`);
    const saved = current(equilibrium);
    return {equilibrium_job: saved?.job ?? null, operation: node.type,
      companion_id: file?.id ?? null, use_physical_density: Boolean(source),
      allow_parent_density: node.type === 'density' && node.settings.parentDensity,
      include_reference_properties: node.type === 'density' && node.settings.references};
  }

  function signature(node) {
    return JSON.stringify(jobInputs(node));
  }

  function current(node) {
    const saved = results.get(node.id);
    if (!saved) return null;
    try { return saved.key === signature(node) ? saved : null; }
    catch { return null; }
  }

  async function perform(node, force = false) {
    if (cancelled) return;
    if (node.type !== 'equilibrium') {
      // Validate branch connections before spending time on its prerequisite.
      jobInputs(node);
      const equilibrium = upstream(node, 'phase');
      if (!current(equilibrium)) await perform(equilibrium);
    }
    if (cancelled || (!force && current(node))) return;
    const input = jobInputs(node);
    const key = JSON.stringify(input);
    const path = node.type === 'equilibrium' ? '/api/workflow/equilibrium' : '/api/workflow/branch';
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
          const unavailable = result.kawin?.state === 'unavailable' ||
            (result.properties && result.properties.density?.state !== 'estimated');
          report(node, unavailable ? 'Unavailable · inspect coverage' : 'Complete', 100);
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
    results, current, upstream,
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
