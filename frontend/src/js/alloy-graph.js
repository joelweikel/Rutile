const pin = (label, type) => ({label, type});
const phase = pin('Phase Set', 'phase');
const assessment = pin('Assessment', 'assessment');
const physical = pin('Physical Data', 'physical');
const mobility = pin('Mobility Data', 'mobility');
export const families = ['AL', 'FE', 'MG', 'MO', 'NI', 'TI'];
export const operations = {
  composition: {title: 'Composition', group: 'input', outputs: {composition: pin('Composition', 'composition')},
    settings: {base: 'AL', element: 'CU', amount: 4, basis: 'mass'}},
  sources: {title: 'MatCalc Sources', group: 'source', inputs: {
    assessment: pin('Thermodynamic File', 'assessment'), physical: pin('Physical Data File', 'physical'),
    mobility: pin('Mobility File', 'mobility')}, outputs: {assessment, physical, mobility}, settings: {family: 'AL'}},
  assessmentFile: {title: 'Thermodynamic File', group: 'source', outputs: {file: assessment}, settings: {file: null}},
  physicalFile: {title: 'Physical Data File', group: 'source', outputs: {file: physical}, settings: {file: null}},
  mobilityFile: {title: 'Mobility File', group: 'source', outputs: {file: mobility}, settings: {file: null}},
  schedule: {title: 'Processing Schedule', group: 'input', outputs: {schedule: pin('Schedule', 'schedule')},
    settings: {initial: 298.15, melt: 1873.15, final: 298.15, pressure: 101325, points: 21}},
  equilibrium: {title: 'Equilibrium Along Schedule', group: 'model', run: true, inputs: {
    composition: pin('Composition', 'composition'), assessment, schedule: pin('Schedule', 'schedule')},
    outputs: {phase: {...phase, label: 'Final Phase Set'}}, settings: {}},
  density: {title: 'Density', group: 'property', run: true, inputs: {phase, physical},
    outputs: {result: pin('Density', 'density')}, settings: {references: true, parentDensity: false}},
  tracer: {title: 'Tracer Diffusivity', group: 'property', run: true, inputs: {phase, mobility},
    outputs: {result: pin('Tracer Diffusivities', 'tracer')}, settings: {}},
  viewer: {title: 'Phase Viewer', group: 'viewer', inputs: {phase}, settings: {}},
};

export function nodeOf(type, x, y, id = crypto.randomUUID()) {
  return {id, type, x, y, settings: structuredClone(operations[type].settings)};
}

const starterSourceY = 234;
const starterScheduleY = 490;

export function starter() {
  return {version: 1, name: 'Al–Cu equilibrium', nodes: [
    nodeOf('composition', 0, 0, 'composition'), nodeOf('sources', 0, starterSourceY, 'sources'),
    nodeOf('schedule', 0, starterScheduleY, 'schedule'), nodeOf('equilibrium', 314, 211, 'equilibrium'),
    nodeOf('viewer', 628, 0, 'viewer'), nodeOf('density', 628, 128, 'density'),
    nodeOf('tracer', 628, 320, 'tracer'),
  ], edges: [
    ['composition', 'composition', 'equilibrium', 'composition'],
    ['sources', 'assessment', 'equilibrium', 'assessment'],
    ['schedule', 'schedule', 'equilibrium', 'schedule'],
    ['equilibrium', 'phase', 'viewer', 'phase'],
    ['equilibrium', 'phase', 'density', 'phase'],
    ['equilibrium', 'phase', 'tracer', 'phase'],
    ['sources', 'physical', 'density', 'physical'],
    ['sources', 'mobility', 'tracer', 'mobility'],
  ]};
}

export function accepts(graph, edge) {
  const [from, output, to, input] = edge;
  const source = graph.nodes.find(node => node.id === from);
  const target = graph.nodes.find(node => node.id === to);
  const left = operations[source?.type]?.outputs?.[output];
  const right = operations[target?.type]?.inputs?.[input];
  if (!left || !right || left.type !== right.type) return false;
  const pending = [to], seen = new Set();
  while (pending.length) {
    const id = pending.pop();
    if (id === from) return false;
    if (seen.has(id)) continue;
    seen.add(id);
    pending.push(...graph.edges.filter(wire => wire[0] === id).map(wire => wire[2]));
  }
  return true;
}

export function restoreGraph(data) {
  if (data?.version !== 1 || typeof data.name !== 'string' || !Array.isArray(data.nodes) ||
      !Array.isArray(data.edges) || data.nodes.length > 100 || data.edges.length > 300) throw new Error('Invalid Alloy Studio workflow.');
  const graph = {version: 1, name: data.name.slice(0, 100), nodes: [], edges: []};
  for (const node of data.nodes) {
    if (!Object.hasOwn(operations, node.type) || typeof node.id !== 'string' || !/^[\w-]{1,64}$/.test(node.id) ||
        graph.nodes.some(peer => peer.id === node.id) || !Number.isFinite(node.x) || !Number.isFinite(node.y)) {
      throw new Error('The workflow has an invalid node.');
    }
    const restored = nodeOf(node.type, Math.max(-10000, Math.min(10000, node.x)), Math.max(-10000, Math.min(10000, node.y)), node.id);
    for (const [key, initial] of Object.entries(restored.settings)) {
      const value = node.settings?.[key];
      if (initial === null) {
        if (typeof value?.id === 'string' && /^[a-f0-9]{64}$/.test(value.id) && typeof value.name === 'string') {
          restored.settings[key] = {id: value.id, name: value.name.slice(0, 240)};
        }
      } else if (typeof value === typeof initial && (typeof value !== 'number' || Number.isFinite(value))) {
        restored.settings[key] = value;
      }
    }
    graph.nodes.push(restored);
  }
  for (const edge of data.edges) {
    if (!Array.isArray(edge) || edge.length < 4 || edge.length > 5 || !accepts(graph, edge) ||
        graph.edges.some(wire => wire[2] === edge[2] && wire[3] === edge[3])) throw new Error('The workflow has an invalid connection.');
    const [from, output, to, input, route = []] = edge;
    if (!Array.isArray(route) || route.length > 100 ||
        route.some(point => !Number.isFinite(point?.x) || !Number.isFinite(point?.y))) {
      throw new Error('The workflow has an invalid wire route.');
    }
    const wire = [from, output, to, input];
    if (route.length) wire.push(route.map(({x, y}) => ({
      x: Math.max(-10000, Math.min(10000, x)), y: Math.max(-10000, Math.min(10000, y)),
    })));
    graph.edges.push(wire);
  }
  // Older starters used shorter summary-only cards. Expand the original
  // left column when those cards still occupy their original positions.
  const original = (id, ys) => graph.nodes.find(node => node.id === id && node.type === id && node.x === 0 && ys.includes(node.y));
  const source = original('sources', [129]);
  const schedule = original('schedule', [313, 363]);
  if (original('composition', [0]) && source && schedule) {
    source.y = starterSourceY;
    schedule.y = starterScheduleY;
  }
  return graph;
}
