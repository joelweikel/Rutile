import {dot, labGem, naturalGem} from './gem-models.js';
import {createGemRenderer} from './gem-optics.js';

const TAU = 2 * Math.PI;
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
const mix = (a, b, t) => a + (b - a) * t;
const subtract = (a, b) => a.map((value, axis) => value - b[axis]);
const noise = index => ((Math.sin(index * 78.233 + 17.19) * 43758.5453) % 1 + 1) % 1;
const diveDuration = 1490;
const latticeEntryZoom = .68;
const latticeEntryDistance = 4.8;
const latticeRestDistance = 7;
const latticeDepths = [-2, -.65, .65];

const latticeCenter = (width, height) => [width * (width <= 720 ? .54 : .60), height * .51];

function depthZoom(zoom, distance, depth) {
  // Convert the focal length and camera distance to magnification at this depth.
  return zoom * (distance / latticeRestDistance) * (latticeRestDistance - depth) / (distance - depth);
}

function depthLayer(depth) {
  return depth < -1.325 ? 0 : depth < 0 ? 1 : 2;
}

function smooth(start, end, value) {
  const t = clamp((value - start) / (end - start), 0, 1);
  return t * t * (3 - 2 * t);
}

function rotation(x, y, z) {
  const cx = Math.cos(x), sx = Math.sin(x);
  const cy = Math.cos(y), sy = Math.sin(y);
  const cz = Math.cos(z), sz = Math.sin(z);
  return ([a, b, c]) => {
    const u = a * cy + c * sy;
    const depth = c * cy - a * sy;
    const v = b * cx - depth * sx;
    return [u * cz - v * sz, u * sz + v * cz, b * sx + depth * cx];
  };
}

function makeLattice() {
  // Rutile P4₂/mnm, with the tetragonal c axis drawn vertically.
  const u = .3053;
  const basis = [
    ['Ti', 0, 0, 0], ['Ti', .5, .5, .5],
    ['O', u, u, 0], ['O', 1 - u, 1 - u, 0],
    ['O', .5 + u, .5 - u, .5], ['O', .5 - u, .5 + u, .5],
  ];
  const atoms = [];
  const turn = rotation(-.36, .51, -.25);
  for (let x = -3; x <= 3; x++) {
    for (let y = -3; y <= 3; y++) {
      for (let z = -3; z <= 3; z++) {
        for (const [element, a, b, c] of basis) {
          const position = turn([x + a - .42, (z + c - .42) * .644, y + b - .42]);
          if (position[2] > -3.2 && position[2] < 1.26) atoms.push({element, position, neighbours: []});
        }
      }
    }
  }
  atoms.sort((a, b) => a.position[2] - b.position[2]);
  for (const [a, atom] of atoms.entries()) {
    for (let b = a + 1; b < atoms.length; b++) {
      const other = atoms[b];
      if (other.position[2] - atom.position[2] >= .45) break;
      if (atom.element === other.element) continue;
      const delta = subtract(atom.position, other.position);
      if (dot(delta, delta) >= .45 ** 2) continue;
      atom.neighbours.push(b);
      other.neighbours.push(a);
    }
  }
  return atoms;
}

const lattice = makeLattice();
const rays = Array.from({length: 28}, (_, i) => ({
  angle: (i + .65 * noise(i + 31)) * TAU / 28,
  length: .23 + .79 * noise(i + 210) ** 1.3,
  width: .001 + .026 * noise(i + 440) ** 4,
  hue: [193, 206, 38, 15, 282, 165][i % 6],
  strength: .22 + .63 * noise(i + 91),
}));

function polygon(ctx, points) {
  ctx.beginPath();
  ctx.moveTo(points[0][0], points[0][1]);
  for (const [x, y] of points.slice(1)) ctx.lineTo(x, y);
  ctx.closePath();
}

function glow(ctx, x, y, size, inner) {
  const light = ctx.createRadialGradient(x, y, 0, x, y, size);
  light.addColorStop(0, inner);
  light.addColorStop(1, 'transparent');
  ctx.fillStyle = light;
  ctx.fillRect(x - size, y - size, size * 2, size * 2);
}

function drawRays(ctx, point, scale, angle, strength) {
  const [x, y] = point;
  ctx.save();
  ctx.globalCompositeOperation = 'screen';
  glow(ctx, x, y, scale * .56, `rgba(183, 215, 246, ${strength * .32})`);
  for (const ray of rays) {
    const heading = ray.angle + angle;
    const dx = Math.cos(heading), dy = Math.sin(heading);
    const length = ray.length * scale;
    const spread = ray.width * scale;
    const beam = ctx.createLinearGradient(x, y, x + dx * length, y + dy * length);
    const alpha = ray.strength * strength;
    beam.addColorStop(0, `rgba(255, 255, 255, ${alpha})`);
    beam.addColorStop(.13, `rgba(224, 244, 255, ${alpha * .87})`);
    beam.addColorStop(.32, `hsla(${ray.hue}, 96%, 74%, ${alpha * .82})`);
    beam.addColorStop(.84, `hsla(${ray.hue}, 95%, 62%, ${alpha * .15})`);
    beam.addColorStop(1, 'transparent');
    polygon(ctx, [
      [x - dy * spread * .17, y + dx * spread * .17],
      [x + dx * length * .38 + dy * spread, y + dy * length * .38 - dx * spread],
      [x + dx * length, y + dy * length],
      [x + dx * length * .52 - dy * spread * .28, y + dy * length * .52 + dx * spread * .28],
    ]);
    ctx.fillStyle = beam;
    ctx.fill();
  }
  glow(ctx, x, y, scale * .12, `rgba(240, 249, 255, ${strength * .74})`);
  ctx.restore();
}

function drawFallbackGem(ctx, gem, project, turn, scale, pose, natural) {
  const points = gem.vertices.map(project);
  const sorted = gem.faces.map((face, index) => ({
    points: face.ids.map(id => points[id]),
    normal: turn(face.normal),
    seed: noise(index + 700),
  }));
  sorted.sort((a, b) => a.points.reduce((sum, p) => sum + p[2], 0) -
    b.points.reduce((sum, p) => sum + p[2], 0));

  ctx.save();
  ctx.globalAlpha = pose.gem;
  for (const {points: triangle, normal, seed} of sorted) {
    const [a, b, c] = triangle;
    const lamp = Math.max(0, dot(normal, [-.31, -.51, .8]));
    const rim = Math.max(0, dot(normal, [.69, .25, .68])) ** 7;
    const sparkle = lamp ** 13;
    const hue = natural ? 352 + seed * 17 : 191 + seed * 34;
    const saturation = natural ? 63 + seed * 17 : 9 + seed * 24;
    const base = natural ? 8 + 17 * lamp : 9 + 32 * lamp;
    const highlight = Math.min(98, base + 36 * rim + 49 * sparkle + 21 * seed);
    const fill = ctx.createLinearGradient(a[0], a[1], c[0], c[1]);
    fill.addColorStop(0, `hsl(${hue}, ${saturation}%, ${highlight}%)`);
    fill.addColorStop(.43, `hsl(${hue}, ${saturation}%, ${base + 9 * rim}%)`);
    fill.addColorStop(.74, `hsl(${hue + 8}, ${saturation}%, ${base * .62}%)`);
    fill.addColorStop(1, `hsl(${hue}, ${saturation}%, ${base + 15 * lamp}%)`);
    polygon(ctx, triangle);
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.strokeStyle = natural
      ? `rgba(255, 184, 166, ${.06 + .38 * rim + .25 * sparkle})`
      : `rgba(217, 240, 255, ${.11 + .38 * rim + .3 * sparkle})`;
    ctx.lineWidth = Math.max(.7, Math.min(1.7, scale / 300));
    ctx.stroke();

    if (seed > .24 && normal[2] > -.06) {
      const corner = a.map((value, i) => mix(value, b[i], .17 + seed * .2));
      const tip = b.map((value, i) => mix(value, c[i], .88));
      const edge = a.map((value, i) => mix(value, c[i], .61 + seed * .18));
      const glint = ctx.createLinearGradient(corner[0], corner[1], tip[0], tip[1]);
      glint.addColorStop(0, 'transparent');
      glint.addColorStop(.58, `hsla(${natural ? 19 : hue + (seed - .5) * 100}, 88%, 81%, ${.06 + .18 * lamp + .39 * rim})`);
      glint.addColorStop(1, 'transparent');
      polygon(ctx, [corner, tip, edge]);
      ctx.fillStyle = glint;
      ctx.fill();
    }
  }
  ctx.restore();
}

function drawAtom(ctx, atom, neighbours, scale) {
  const {element, x, y, radius, visibility} = atom;
  const ti = element === 'Ti';
  const tint = ti ? '117, 186, 255' : '255, 47, 83';
  const glass = ctx.createRadialGradient(x - radius * .30, y - radius * .43, 0, x, y, radius);
  glass.addColorStop(0, ti ? '#b4d5ff60' : '#e86b815e');
  glass.addColorStop(.55, ti ? '#32659b51' : '#7e1e3a69');
  glass.addColorStop(.85, ti ? '#10182b81' : '#310b177f');
  glass.addColorStop(1, ti ? '#76baff88' : '#f83e5f96');

  const rim = ctx.createLinearGradient(x - radius, y - radius, x + radius, y + radius);
  rim.addColorStop(0, ti ? '#eff7ff' : '#ffabb6');
  rim.addColorStop(.34, ti ? '#a0c8f9b5' : '#ff6888ba');
  rim.addColorStop(.67, ti ? '#679cdf45' : '#e83a5f58');
  rim.addColorStop(1, ti ? '#c6e5ffd9' : '#ff7a91');

  ctx.save();
  ctx.globalAlpha *= visibility;
  glow(ctx, x, y, radius * 1.72, `rgba(${tint}, .29)`);
  ctx.beginPath();
  ctx.arc(x, y, radius, 0, TAU);
  ctx.fillStyle = glass;
  ctx.fill();
  ctx.strokeStyle = rim;
  ctx.lineWidth = clamp(scale * .0035, .8, 2);
  ctx.stroke();

  // Light from the closest visible bonded neighbour strikes the rim facing it.
  let reflection;
  let strength = .08;
  for (const other of neighbours) {
    if (other.visibility < .04) continue;
    const dx = other.x - x, dy = other.y - y;
    const separation = Math.hypot(dx, dy);
    if (separation < radius * .42) continue;
    const intensity = other.visibility * Math.exp(-Math.max(0, separation - radius - other.radius) / (radius * 1.8));
    if (intensity > strength) {
      strength = intensity;
      reflection = [dx / separation, dy / separation];
    }
  }
  if (reflection) {
    const [dx, dy] = reflection;
    const light = ti ? '255, 53, 91' : '162, 212, 255';
    const hx = x + dx * radius * .92, hy = y + dy * radius * .92;
    glow(ctx, hx, hy, radius * .71, `rgba(${light}, ${strength * .48})`);
    const bounce = ctx.createLinearGradient(x, y, x + dx * radius, y + dy * radius);
    bounce.addColorStop(0, 'transparent');
    bounce.addColorStop(.57, `rgba(${light}, ${strength * .45})`);
    bounce.addColorStop(1, `rgba(${light}, ${Math.min(1, strength * 1.65)})`);
    ctx.strokeStyle = bounce;
    ctx.lineWidth = clamp(radius * .074, 1, 3.1);
    ctx.stroke();
  }

  ctx.fillStyle = ti ? '#f2f9ff' : '#fff0f4';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.font = `650 ${radius * .79}px Estedad, sans-serif`;
  ctx.shadowColor = ti ? '#a1d2ff' : '#ff3758';
  ctx.shadowBlur = radius * .37;
  ctx.fillText(element, x, y + .5);
  ctx.restore();
}

function drawLattice(layers, width, height) {
  const scale = Math.max(Math.min(width, height) * .68, width * .27, height * .43);
  const project = projection(point => point, scale, latticeCenter(width, height), latticeRestDistance);
  const atoms = lattice.map(({element, position, neighbours}) => {
    const [x, y, depth, perspective] = project(position);
    const distance = 1.16 - depth;
    const edge = smooth(-.06, .16, x / width) * (1 - smooth(.84, 1.06, x / width));
    const visibility = edge * smooth(-.10, .25, distance) *
      Math.exp(-Math.max(0, distance - .26) * 1.30);
    const radius = scale * perspective * (element === 'Ti' ? .105 : .077);
    const margin = radius * 1.8;
    const layer = layers[depthLayer(depth)];
    const bounds = layer.bounds;
    const inLayer = x > bounds.x - margin && x < bounds.x + bounds.width + margin &&
      y > bounds.y - margin && y < bounds.y + bounds.height + margin;
    return {element, neighbours, x, y, depth, radius, visibility, layer, inLayer};
  });
  for (const {ctx} of layers) ctx.lineWidth = clamp(scale * .004, .5, 1.5);
  for (const atom of atoms) {
    if (atom.element !== 'Ti' || atom.visibility < .08) continue;
    for (const id of atom.neighbours) {
      const other = atoms[id];
      if (!atom.inLayer && !other.inLayer) continue;
      const alpha = Math.min(atom.visibility, other.visibility) * .14;
      if (alpha < .008) continue;
      const {ctx} = layers[depthLayer((atom.depth + other.depth) / 2)];
      ctx.strokeStyle = `rgba(156, 184, 222, ${alpha})`;
      ctx.beginPath();
      ctx.moveTo(atom.x, atom.y);
      ctx.lineTo(other.x, other.y);
      ctx.stroke();
    }
  }
  for (const atom of atoms) {
    if (atom.inLayer && atom.visibility > .04) {
      drawAtom(atom.layer.ctx, atom, atom.neighbours.map(id => atoms[id]), scale);
    }
  }
}

function projection(turn, scale, [cx, cy], distance) {
  return point => {
    const [x, y, depth] = turn(point);
    const perspective = distance / Math.max(1.2, distance - depth);
    return [cx + x * scale * perspective, cy + y * scale * perspective, depth, perspective];
  };
}

export function createRutileScene(canvas, gemCanvas) {
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;
  let optics = createGemRenderer(gemCanvas);
  gemCanvas.dataset.renderer = optics ? 'webgl' : 'canvas';

  let width = 1, height = 1;
  let screen = 'loading', natural = false, reduced = false;
  let pose, dive, frame, latticeLayers, lastTime = 0, titleAge = 0, orbit = 0, yaw = 0, tilt = 0;

  function prepareLattice() {
    if (latticeLayers) return;
    // Cache each depth at its widest view so the lens can move without exposing an edge.
    const [cx, cy] = latticeCenter(width, height);
    const layers = latticeDepths.map(depth => {
      const widest = depthZoom(latticeEntryZoom, latticeEntryDistance, depth);
      return {depth, bounds: {
        x: cx * (1 - 1 / widest), y: cy * (1 - 1 / widest),
        width: width / widest, height: height / widest,
      }};
    });
    const area = layers.reduce((total, {bounds}) => total + bounds.width * bounds.height, 0);
    const ratio = Math.min(canvas.width / width, canvas.height / height,
      Math.sqrt(6_000_000 / area));
    latticeLayers = layers.map(({depth, bounds}) => {
      const image = document.createElement('canvas');
      image.width = Math.ceil(bounds.width * ratio);
      image.height = Math.ceil(bounds.height * ratio);
      const context = image.getContext('2d');
      const scaleX = image.width / bounds.width, scaleY = image.height / bounds.height;
      context.setTransform(scaleX, 0, 0, scaleY, -bounds.x * scaleX, -bounds.y * scaleY);
      return {image, ctx: context, depth, bounds};
    });
    drawLattice(latticeLayers, width, height);
  }

  function targetPose() {
    const mobile = width <= 720;
    const angle = .68 + orbit + yaw;
    const pitch = natural ? 0 : -.90;
    const size = natural ? .345 : .28;
    const title = {x: .23 + pitch + tilt, y: angle, z: .44, cx: mobile ? .55 : .70,
      cy: mobile ? .50 : .51, scale: mobile ? Math.min(size, height * .2 / Math.min(width, height)) : size,
      distance: 4.8, gem: 1, lattice: 0, latticeZoom: 1, latticeDistance: latticeRestDistance,
      rays: natural || reduced ? 0 : .53};
    if (screen === 'loading') return {...title, scale: .045, gem: 0, rays: 0, y: angle - .7};
    if (screen === 'title') return title;
    const surface = {...title, x: .64 + pitch, y: angle + .65, z: 1.12, cx: mobile ? .62 : .75,
      cy: mobile ? .77 : .73, scale: mobile ? .94 : 1.05, rays: natural || reduced ? 0 : .14};
    if (screen === 'menu') return surface;
    return {...surface, cx: .78, cy: .64, scale: 2.05, gem: 0, lattice: 1, rays: 0};
  }

  function divePose(time, target) {
    const {from, start} = dive;
    const t = (time - start) / diveDuration;
    if (t >= 1) {
      dive = undefined;
      return target;
    }
    const push = smooth(0, .70, t);
    const inside = smooth(.31, 1, t);
    const lens = 1 - .19 * Math.sin(Math.PI * push);
    return {
      ...target,
      x: mix(from.x, from.x + .14, push),
      y: mix(from.y, target.y, push),
      z: mix(from.z, target.z, push),
      cx: mix(from.cx, .53, push),
      cy: mix(from.cy, .52, push),
      scale: from.scale * (9 / from.scale) ** push * lens,
      distance: mix(from.distance, 1.21, push),
      gem: from.gem * (1 - smooth(.49, .83, t)),
      rays: from.rays * (1 - smooth(.14, .45, t)),
      lattice: smooth(.27, .72, t),
      latticeZoom: mix(latticeEntryZoom, 1, inside),
      latticeDistance: mix(latticeEntryDistance, latticeRestDistance, inside),
    };
  }

  function draw(time) {
    frame = undefined;
    // Keep the gem and lattice in sync. A busy GPU gets the newest pose once its last draw completes.
    if (dive && time - dive.start < diveDuration * .83 && optics?.available && !optics.readyForFrame()) {
      schedule();
      return;
    }
    const dt = lastTime ? clamp((time - lastTime) / 1000, 0, .065) : 0;
    lastTime = time;
    const orbiting = screen === 'title' || screen === 'menu';
    if (!reduced && orbiting) {
      titleAge += dt;
      orbit += dt * (screen === 'title' ? .29 + 1.34 * Math.exp(-titleAge * 1.8) : .012);
    }
    const target = targetPose();
    if (dive) pose = divePose(time, target);
    else if (!pose || reduced) pose = target;
    else {
      const ease = 1 - Math.exp(-dt * 4.5);
      for (const key of Object.keys(target)) pose[key] = mix(pose[key], target[key], ease);
    }
    const settling = Object.keys(target).some(key => Math.abs(pose[key] - target[key]) > .002);
    if (!dive && !orbiting && !settling) pose = target;
    ctx.clearRect(0, 0, width, height);

    const unit = Math.min(width, height);
    if (pose.gem > .005) {
      const center = [width * pose.cx, height * pose.cy];
      const scale = unit * pose.scale;
      const turn = rotation(pose.x, pose.y, pose.z);
      ctx.save();
      ctx.globalAlpha = pose.gem;
      glow(ctx, ...center, Math.min(unit * 1.3, scale * 2.1), natural ? '#46141b25' : '#314d632a');
      ctx.restore();
      const project = projection(turn, scale, center, pose.distance);
      if (optics?.available) optics.draw(turn, width, height, unit, pose, natural, Boolean(dive));
      else drawFallbackGem(ctx, natural ? naturalGem : labGem, project, turn, scale, pose, natural);
      if (!natural && pose.rays > .01) {
        drawRays(ctx, project([.1, -.16, .72]), scale * 1.8, pose.z * .4 + pose.y * .12, pose.rays);
        drawRays(ctx, project([-.45, .10, .29]), scale * .79, pose.z, pose.rays * .4);
      }
    } else if (optics?.available) {
      optics.clear();
    }
    if (pose.lattice > .005) {
      prepareLattice();
      const [cx, cy] = latticeCenter(width, height);
      ctx.globalAlpha = pose.lattice;
      for (const {image, depth, bounds} of latticeLayers) {
        const zoom = depthZoom(pose.latticeZoom, pose.latticeDistance, depth);
        ctx.drawImage(image, cx * (1 - zoom) + bounds.x * zoom,
          cy * (1 - zoom) + bounds.y * zoom, bounds.width * zoom, bounds.height * zoom);
      }
      ctx.globalAlpha = 1;
    }
    if (!reduced && screen !== 'loading' && (orbiting || dive || settling)) schedule();
  }

  function schedule() {
    if (frame === undefined && !document.hidden) frame = requestAnimationFrame(draw);
  }

  function resize() {
    const bounds = canvas.getBoundingClientRect();
    const ratio = Math.min(window.devicePixelRatio || 1, 1.75);
    width = Math.max(1, bounds.width);
    height = Math.max(1, bounds.height);
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    latticeLayers = undefined;
    if (optics?.available) optics.resize(width, height, screen === 'title', Boolean(dive));
    schedule();
  }

  window.addEventListener('resize', resize);
  gemCanvas.addEventListener('webglcontextlost', event => {
    event.preventDefault();
    gemCanvas.dataset.renderer = 'canvas';
    schedule();
  });
  gemCanvas.addEventListener('webglcontextrestored', () => {
    optics = createGemRenderer(gemCanvas);
    gemCanvas.dataset.renderer = optics ? 'webgl' : 'canvas';
    resize();
  });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      cancelAnimationFrame(frame);
      frame = undefined;
      lastTime = 0;
    } else {
      schedule();
    }
  });
  document.fonts.ready.then(() => {
    latticeLayers = undefined;
    prepareLattice();
    schedule();
  });
  resize();

  return {
    setView(view) {
      const enter = (view === 'settings' || view === 'diagrams') &&
        (screen === 'menu' || screen === 'title') && !reduced && pose?.gem > .05;
      if (screen === 'loading' && view === 'title') {
        pose = targetPose();
        titleAge = 0;
      }
      screen = view;
      lastTime = performance.now();
      dive = enter ? {from: {...pose}, start: lastTime} : undefined;
      if (optics?.available && (enter || view === 'menu' || view === 'title')) {
        optics.resize(width, height, view === 'title', enter);
      }
      schedule();
      return enter;
    },
    setPreferences(specimen, reduce) {
      natural = specimen === 'natural';
      reduced = reduce;
      if (reduce) dive = undefined;
      schedule();
    },
    rotate(dx, dy) {
      yaw += dx * .009;
      tilt = clamp(tilt + dy * .007, -1.05, 1.05);
      schedule();
    },
  };
}
