import {restoreScheduleEvents} from './processing-events.js';

const pin = (label, type) => ({label, type});
const phase = pin('Phase Set', 'phase-set');
const finalPhase = pin('Final Phase Set', 'final-phase-set');
const phaseRecord = pin('Phase Data', 'phase-record');
const assessment = pin('Assessment', 'assessment');
const physical = pin('Physical Data', 'physical');
const mobility = pin('Mobility Data', 'mobility');
export const families = ['AL', 'FE', 'MG', 'MO', 'NI', 'TI'];
export const operations = {
  composition: {title: 'Composition', group: 'input', outputs: {composition: pin('Composition', 'composition')},
    settings: {base: 'AL', element: 'CU', amount: 4, basis: 'mass'}},
  sources: {title: 'Data Sources', group: 'source', inputs: {
    assessment: pin('Thermodynamic File', 'assessment'), physical: pin('Physical Data File', 'physical'),
    mobility: pin('Mobility File', 'mobility')}, outputs: {assessment, physical, mobility},
    settings: {family: '', namedMobility: false, configuredPhysical: false}},
  assessmentFile: {title: 'Thermodynamic File', group: 'source', outputs: {file: assessment}, settings: {file: null, preset: ''}},
  physicalFile: {title: 'Physical Data File', group: 'source', outputs: {file: physical}, settings: {file: null, preset: ''}},
  mobilityFile: {title: 'Mobility File', group: 'source', outputs: {file: mobility}, settings: {file: null, preset: ''}},
  schedule: {title: 'Processing Schedule', group: 'input', outputs: {schedule: pin('Schedule', 'schedule')},
    settings: {initial: 298.15, melt: 1873.15, final: 298.15, pressure: 101325, points: 21, route: 'arc_melting', events: []}},
  equilibrium: {title: 'Equilibrium Along Schedule', group: 'model', run: true, inputs: {
    composition: pin('Composition', 'composition'), assessment, schedule: pin('Schedule', 'schedule')},
    outputs: {phase}, settings: {}},
  phaseAssignment: {title: 'Phase Assignment', group: 'model', run: true, inputs: {phase, physical},
    outputs: {phase: finalPhase}, settings: {references: true, materialIds: {}}},
  phaseData: {title: 'Phase Data', group: 'source', outputs: {data: phaseRecord}, settings: {
    name: '', materialId: '', source: '', origin: 'sourced', temperature_k: '', pressure_pa: '', composition_mole_fraction: '',
    density_g_cm3: '', bulk_modulus_gpa: '', shear_modulus_gpa: '', properties: '', research: '',
  }},
  density: {title: 'Density', group: 'property', run: true, inputs: {
    phase: finalPhase, physical: {...physical, label: 'Physical Data Override'}},
    outputs: {result: pin('Density', 'density')}, settings: {references: true, parentDensity: false}},
  tracer: {title: 'Tracer Diffusivity', group: 'property', run: true, inputs: {phase: finalPhase, mobility},
    outputs: {result: pin('Tracer Diffusivities', 'tracer')}, settings: {}},
  viewer: {title: 'Phase Viewer', group: 'viewer', inputs: {phase: finalPhase}, settings: {}},
};

const phaseKey = /^record_[a-f0-9]{64}$/;
export const materialId = /^(?:(?:mp|mvc)-[0-9]{1,20}|mp-[a-z]{1,20})$/;

export function inputPort(node, key) {
  if (node?.type === 'phaseAssignment' && phaseKey.test(key)) return phaseRecord;
  const inputs = operations[node?.type]?.inputs;
  return inputs && Object.hasOwn(inputs, key) ? inputs[key] : undefined;
}

export function nodeOf(type, x, y, id = crypto.randomUUID()) {
  return {id, type, x, y, settings: structuredClone(operations[type].settings)};
}

const starterSourceY = 234;
const starterScheduleY = 365;
const fileTypes = {assessment: 'assessmentFile', mobility: 'mobilityFile', physical: 'physicalFile'};

function presetFile(role, preset, x, y, id) {
  const node = nodeOf(fileTypes[role], x, y, id);
  node.settings.preset = preset;
  return node;
}

export function starter() {
  const graph = {version: 3, name: 'Al–Cu equilibrium', nodes: [
    nodeOf('composition', 0, 0, 'composition'),
    presetFile('assessment', 'AL', 0, starterSourceY, 'assessment-file'),
    presetFile('physical', 'configured', 314, 76, 'physical-file'),
    presetFile('mobility', 'AL', 0, 300, 'mobility-file'),
    nodeOf('schedule', 0, starterScheduleY, 'schedule'), nodeOf('equilibrium', 314, 211, 'equilibrium'),
    nodeOf('phaseAssignment', 628, 211, 'phase-assignment'),
    nodeOf('viewer', 942, 0, 'viewer'), nodeOf('density', 942, 128, 'density'),
    nodeOf('tracer', 942, 320, 'tracer'),
  ], edges: [
    ['composition', 'composition', 'equilibrium', 'composition'],
    ['assessment-file', 'file', 'equilibrium', 'assessment'],
    ['schedule', 'schedule', 'equilibrium', 'schedule'],
    ['equilibrium', 'phase', 'phase-assignment', 'phase'],
    ['phase-assignment', 'phase', 'viewer', 'phase'],
    ['phase-assignment', 'phase', 'density', 'phase'],
    ['phase-assignment', 'phase', 'tracer', 'phase'],
    ['physical-file', 'file', 'phase-assignment', 'physical'],
    ['mobility-file', 'file', 'tracer', 'mobility'],
  ]};
  addStarterReferences(graph, graph.nodes.find(node => node.id === 'phase-assignment'));
  return graph;
}

function addStarterReferences(graph, assignment) {
  // IDs bind the pinned Al assessment and the individual solver model label.
  const references = [
    ['GP_MAT · FCC parent', 'mp-134', 'record_a68a97315e99b77ae366f74ee1b7e46a89f7e2fd6acb4150e892d707c92c298c'],
    ['THETA_AL2CU · C16', 'mp-998', 'record_d68245b6f1c476719db7fac0c5aa32b009d06b9a5ba70b54edd206f6f3e4415f'],
  ];
  references.forEach(([name, materialId, key], index) => {
    if (graph.nodes.length >= 200 || graph.edges.length >= 500 || assignment.settings.materialIds[key] ||
        graph.edges.some(edge => edge[2] === assignment.id && edge[3] === key)) return;
    const node = nodeOf('phaseData', Math.max(-10000, assignment.x - 314), Math.min(10000, assignment.y + 220 + index * 67));
    Object.assign(node.settings, {name, materialId});
    graph.nodes.push(node);
    graph.edges.push([node.id, 'data', assignment.id, key]);
  });
}

export function accepts(graph, edge) {
  const [from, output, to, input] = edge;
  const source = graph.nodes.find(node => node.id === from);
  const target = graph.nodes.find(node => node.id === to);
  const outputs = operations[source?.type]?.outputs;
  const left = outputs && Object.hasOwn(outputs, output) ? outputs[output] : undefined;
  const right = inputPort(target, input);
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
  if (![1, 2, 3].includes(data?.version) || typeof data.name !== 'string' || !Array.isArray(data.nodes) ||
      !Array.isArray(data.edges) || data.nodes.length > 200 || data.edges.length > 500) throw new Error('Invalid Alloy Studio workflow.');
  const researchProject = /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/.test(data.researchProject)
    ? data.researchProject : crypto.randomUUID();
  const graph = {version: 3, name: data.name.slice(0, 100), nodes: [], edges: [], researchProject};
  for (const node of data.nodes) {
    if (!Object.hasOwn(operations, node.type) || typeof node.id !== 'string' || !/^[\w-]{1,64}$/.test(node.id) ||
        graph.nodes.some(peer => peer.id === node.id) || !Number.isFinite(node.x) || !Number.isFinite(node.y)) {
      throw new Error('The workflow has an invalid node.');
    }
    const restored = nodeOf(node.type, Math.max(-10000, Math.min(10000, node.x)), Math.max(-10000, Math.min(10000, node.y)), node.id);
    for (const [key, initial] of Object.entries(restored.settings)) {
      const value = node.settings?.[key];
      if (key === 'events') {
        restored.settings.events = restoreScheduleEvents(value);
      } else if (key === 'materialIds') {
        restored.settings.materialIds = Object.fromEntries(Object.entries(value || {}).filter(
          ([key, id]) => phaseKey.test(key) && typeof id === 'string').slice(0, 100).map(
          ([key, id]) => [key, id.trim().toLowerCase().slice(0, 24)]));
      } else if (node.type === 'phaseData' && typeof value === 'string') {
        const limits = {research: 24000, properties: 10000, composition_mole_fraction: 2000};
        restored.settings[key] = value.slice(0, limits[key] || 240);
      } else if (key === 'route') {
        if (value === 'heat_treatment') restored.settings.route = value;
      } else if (node.type === 'schedule' && typeof initial === 'number' && value === null) {
        restored.settings[key] = null;
      } else if (initial === null) {
        if (typeof value?.id === 'string' && /^[a-f0-9]{64}$/.test(value.id) && typeof value.name === 'string') {
          restored.settings[key] = {id: value.id, name: value.name.slice(0, 240)};
        }
      } else if (typeof value === typeof initial && (typeof value !== 'number' || Number.isFinite(value))) {
        restored.settings[key] = value;
      }
    }
    if (node.type === 'sources' && families.includes(restored.settings.family)) {
      restored.settings.namedMobility = node.settings?.namedMobility !== false;
      restored.settings.configuredPhysical = node.settings?.configuredPhysical !== false;
    }
    graph.nodes.push(restored);
  }
  const edges = data.version === 1 ? migratePhaseOutputs(graph, data.edges) : data.edges;
  for (const edge of edges) {
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
  migrateFileNodes(graph);
  if (data.version < 3 && graph.name === 'Al–Cu equilibrium') {
    const link = graph.edges.find(edge => edge[0] === 'equilibrium' && edge[1] === 'phase');
    const assessment = graph.edges.find(edge => edge[2] === 'equilibrium' && edge[3] === 'assessment');
    const assignment = graph.nodes.find(node => node.id === link?.[2] && node.type === 'phaseAssignment');
    if (assignment && graph.nodes.some(node => node.id === assessment?.[0] && node.settings.preset === 'AL')) {
      addStarterReferences(graph, assignment);
    }
  }
  return graph;
}

function migrateFileNodes(graph) {
  const legacy = graph.nodes.filter(node => node.type === 'sources');
  for (const node of legacy) {
    const {family, namedMobility, configuredPhysical} = node.settings;
    const incoming = role => {
      const id = graph.edges.find(edge => edge[2] === node.id && edge[3] === role)?.[0];
      return graph.nodes.find(file => file.id === id && file.type === fileTypes[role])?.id;
    };
    const assessmentOverride = incoming('assessment');
    const presets = {assessment: family, mobility: namedMobility && !assessmentOverride ? family : '',
      physical: configuredPhysical ? 'configured' : ''};
    const positions = {assessment: [node.x, node.y], mobility: [node.x, node.y + 129], physical: [node.x + 314, node.y - 234]};
    for (const role of Object.keys(fileTypes)) {
      const outgoing = graph.edges.filter(edge => edge[0] === node.id && edge[1] === role);
      let id = incoming(role);
      if (!id && (presets[role] || outgoing.length)) {
        const [x, y] = positions[role].map(value => Math.max(-10000, Math.min(10000, value)));
        const file = presetFile(role, presets[role], x, y);
        graph.nodes.push(file);
        id = file.id;
      }
      for (const edge of outgoing) {
        edge[0] = id;
        edge[1] = 'file';
      }
    }
    graph.edges = graph.edges.filter(edge => edge[2] !== node.id);
    graph.nodes = graph.nodes.filter(peer => peer !== node);
  }
  if (graph.nodes.length > 200) throw new Error('The migrated workflow exceeds the graph size limit.');
}

function migratePhaseOutputs(graph, edges) {
  const nodes = new Map(graph.nodes.map(node => [node.id, node]));
  const assignments = new Map();
  const migrated = edges.map(edge => {
    if (!Array.isArray(edge) || edge.length < 4 || edge.length > 5) return edge;
    const [from, output, to, input, route] = edge;
    const source = nodes.get(from), target = nodes.get(to);
    if (source?.type !== 'equilibrium' || output !== 'phase' || input !== 'phase' ||
        !['density', 'tracer', 'viewer'].includes(target?.type)) return edge;
    let assignment = assignments.get(from);
    if (!assignment) {
      assignment = nodeOf('phaseAssignment', Math.min(10000, source.x + 314), source.y);
      assignments.set(from, assignment);
      graph.nodes.push(assignment);
    }
    if (source.id === 'equilibrium' && source.x === 314 && target.x === 628) target.x += 314;
    return route === undefined ? [assignment.id, 'phase', to, input] : [assignment.id, 'phase', to, input, route];
  });
  for (const [equilibrium, assignment] of assignments) {
    migrated.push([equilibrium, 'phase', assignment.id, 'phase']);
    const density = migrated.find(edge => edge?.[0] === assignment.id && nodes.get(edge[2])?.type === 'density');
    const physical = density && edges.find(edge => edge?.[2] === density[2] && edge[3] === 'physical');
    if (physical) migrated.push([physical[0], physical[1], assignment.id, 'physical']);
  }
  if (graph.nodes.length > 200 || migrated.length > 500) throw new Error('The migrated workflow exceeds the graph size limit.');
  return migrated;
}
