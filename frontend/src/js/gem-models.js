const TAU = 2 * Math.PI;
const EPSILON = .0002;
export const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = ([x, y, z], [u, v, w]) => [y * w - z * v, z * u - x * w, x * v - y * u];
const difference = (a, b) => a.map((value, i) => value - b[i]);
const unit = v => v.map(value => value / Math.hypot(...v));

function brilliantPlanes() {
  const planes = [[0, -1, 0, .30], [0, 1, 0, .87]];
  function ring(count, offset, slope, radius) {
    const length = Math.hypot(1, slope);
    for (let i = 0; i < count; i++) {
      const angle = (i + offset) * TAU / count;
      planes.push([Math.cos(angle) / length, slope / length, Math.sin(angle) / length, radius / length]);
    }
  }

  // The crown tapers to an octagonal table. Alternating star and girdle
  // planes break up the silhouette and the reflected pattern in the table.
  ring(16, .5, 0, .98);
  ring(8, 0, -.56 / .38, 1.006);
  ring(8, .5, -2.52, 1.35);
  ring(16, .5, -1.02, 1.001);
  ring(8, 0, 1.155, 1.011);
  ring(16, .5, 1.074, .995);
  return planes;
}

function naturalPlanes() {
  const rings = [
    [-1.20, .23, -.035, .005], [-.98, .35, -.025, 0],
    [-.20, .36, 0, 0], [.83, .35, .02, 0],
    [1.15, .25, .025, .005],
  ];
  const points = rings.flatMap(([height, radius, offset, twist], ring) =>
    Array.from({length: 6}, (_, side) => {
      const angle = (side / 6 + twist) * TAU;
      const uneven = 1 + .11 * Math.sin(ring * 13.7 + side * 2.17);
      return [offset + radius * uneven * Math.cos(angle), height + .09 * Math.sin(side * 1.8 + ring),
        radius * uneven * .82 * Math.sin(angle)];
    })
  );
  const planes = [];
  for (let i = 0; i < points.length - 2; i++) {
    for (let j = i + 1; j < points.length - 1; j++) {
      for (let k = j + 1; k < points.length; k++) {
        const area = cross(difference(points[j], points[i]), difference(points[k], points[i]));
        if (Math.hypot(...area) < EPSILON) continue;
        let normal = unit(area);
        let offset = dot(points[i], normal);
        const distances = points.map(p => dot(p, normal) - offset);
        if (Math.max(...distances) > EPSILON && Math.min(...distances) < -EPSILON) continue;
        if (Math.max(...distances) > EPSILON) {
          normal = normal.map(value => -value);
          offset = -offset;
        }
        if (!planes.some(p => Math.abs(p[3] - offset) < EPSILON && dot(p, normal) > .99999)) {
          planes.push([...normal, offset]);
        }
      }
    }
  }
  return planes;
}

function mesh(planes) {
  const corners = planes.map(() => new Set());
  const vertices = [];
  for (let a = 0; a < planes.length - 2; a++) {
    for (let b = a + 1; b < planes.length - 1; b++) {
      for (let c = b + 1; c < planes.length; c++) {
        const p = planes[a], q = planes[b], r = planes[c];
        const qr = cross(q, r);
        const determinant = dot(p, qr);
        if (Math.abs(determinant) < EPSILON) continue;
        const rp = cross(r, p), pq = cross(p, q);
        const point = qr.map((value, axis) => (p[3] * value + q[3] * rp[axis] + r[3] * pq[axis]) / determinant);
        if (planes.some(plane => dot(plane, point) - plane[3] > EPSILON)) continue;
        let id = vertices.findIndex(vertex => Math.hypot(...difference(vertex, point)) < EPSILON);
        if (id < 0) id = vertices.push(point) - 1;
        for (const face of [a, b, c]) corners[face].add(id);
      }
    }
  }

  const faces = [], activePlanes = [];
  for (const [index, ids] of corners.entries()) {
    if (ids.size < 3) continue;
    const plane = planes[index];
    const normal = plane.slice(0, 3);
    const center = [0, 1, 2].map(axis => [...ids].reduce((sum, id) => sum + vertices[id][axis], 0) / ids.size);
    const tangent = unit(difference(vertices[ids.values().next().value], center));
    const bitangent = cross(normal, tangent);
    const angle = id => {
      const delta = difference(vertices[id], center);
      return Math.atan2(dot(delta, bitangent), dot(delta, tangent));
    };
    const polygon = [...ids].sort((a, b) => angle(a) - angle(b));
    activePlanes.push(plane);
    for (let i = 1; i < polygon.length - 1; i++) {
      faces.push({ids: [polygon[0], polygon[i], polygon[i + 1]], normal});
    }
  }
  return {vertices, faces, planes: activePlanes};
}

export const labGem = mesh(brilliantPlanes());
export const naturalGem = mesh(naturalPlanes());
