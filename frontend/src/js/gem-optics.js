import {labGem, naturalGem} from './gem-models.js';

const vertexShader = `#version 300 es
layout(location = 0) in vec3 position;
layout(location = 1) in vec3 normal;
uniform mat3 turn;
uniform vec2 center;
uniform vec2 zoom;
uniform float distanceToGem;
out vec3 surface;
flat out vec3 facet;
void main() {
  surface = position;
  facet = normal;
  vec3 point = turn * position;
  float depth = distanceToGem - point.z;
  gl_Position = vec4(center * depth + zoom * point.xy, .995 * depth - .15, depth);
}`;

const fragmentShader = `#version 300 es
precision highp float;
in vec3 surface;
flat in vec3 facet;
uniform mat3 turn;
uniform vec3 eye;
uniform vec4 planes[80];
uniform int planeCount;
uniform bool natural;
uniform float opacity;
out vec4 fragment;

float softbox(vec3 ray, vec3 direction, vec2 size, float feather) {
  vec3 side = normalize(cross(vec3(0., 1., 0.), direction));
  vec3 up = cross(direction, side);
  float facing = dot(ray, direction);
  if (facing < .05) return 0.;
  vec2 uv = abs(vec2(dot(ray, side), dot(ray, up)) / facing);
  vec2 edge = 1. - smoothstep(size - feather, size + feather, uv);
  return edge.x * edge.y;
}

vec3 studio(vec3 r) {
  vec3 light = mix(vec3(.009, .014, .025), vec3(.26, .28, .31), 1. - smoothstep(-.95, .48, r.y));
  light += vec3(3.5, 3.7, 4.) * softbox(r, vec3(-.54, -.62, .57), vec2(.45, .28), .055);
  light += vec3(3.7, 4.2, 5.5) * softbox(r, vec3(.85, -.14, .51), vec2(.10, .73), .018);
  light += vec3(5.1, 4.45, 3.72) * softbox(r, vec3(.28, -.68, -.68), vec2(.42, .15), .023);
  light += vec3(1.1, 1.35, 1.71) * softbox(r, vec3(-.48, .60, -.64), vec2(.31, .34), .10);
  light += vec3(2.9, 2.8, 2.7) * softbox(r, vec3(.20, .74, .64), vec2(.21, .074), .02);
  return light;
}

vec3 environment(vec3 ray) {
  return studio(turn * ray);
}

float fresnel(float cosine, float index) {
  float f0 = (index - 1.) / (index + 1.);
  return mix(f0 * f0, 1., pow(1. - clamp(cosine, 0., 1.), 5.));
}

float exitDistance(vec3 p, vec3 ray, out vec3 normal) {
  float nearest = 100.;
  normal = vec3(0.);
  for (int i = 0; i < planeCount; ++i) {
    vec4 plane = planes[i];
    float angle = dot(plane.xyz, ray);
    if (angle <= .0001) continue;
    float offset = plane.w - dot(plane.xyz, p);
    // Compare before dividing. Only the next candidate surface needs a distance.
    if (offset <= .00005 * angle || offset >= nearest * angle) continue;
    nearest = offset / angle;
    normal = plane.xyz;
  }
  return nearest;
}

float hash(vec3 p) {
  p = fract(p * .3183099 + .17) * 17.;
  return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}

float grain(vec3 p) {
  vec3 i = floor(p), f = fract(p);
  f = f * f * (3. - 2. * f);
  return mix(
    mix(mix(hash(i), hash(i + vec3(1,0,0)), f.x),
        mix(hash(i + vec3(0,1,0)), hash(i + vec3(1,1,0)), f.x), f.y),
    mix(mix(hash(i + vec3(0,0,1)), hash(i + vec3(1,0,1)), f.x),
        mix(hash(i + vec3(0,1,1)), hash(i + vec3(1,1,1)), f.x), f.y), f.z);
}

void main() {
  vec3 incident = normalize(surface - eye);
  vec3 normal = facet;
  float veins = 0.;
  if (natural) {
    vec3 detail = surface * 4.;
    veins = grain(detail * vec3(55., 8., 55.)) * .65 + grain(detail * vec3(168., 24., 168.)) * .35;
    vec3 streak = vec3(
      grain(detail * vec3(72., 5., 40.)), grain(detail * 38.),
      grain(detail * vec3(43., 7., 81.))) - .5;
    normal = normalize(normal + streak * (.075 + .13 * veins));
  }

  float index = natural ? 2.54 : 2.64;
  float reflectance = fresnel(-dot(incident, normal), index);
  vec3 reflection = environment(reflect(incident, normal));
  vec3 color = reflection * reflectance * (natural ? vec3(.50, .28, .24) : vec3(1.));
  vec3 ray = refract(incident, facet, 1. / index);
  vec3 point = surface + ray * .00025;
  vec3 energy = vec3(1. - reflectance);
  for (int bounce = 0; bounce < 4; ++bounce) {
    vec3 wall;
    float length = exitDistance(point, ray, wall);
    if (length >= 100.) break;
    point += ray * length;
    if (natural) energy *= exp(-vec3(.42, 3.25, 5.2) * length * (.72 + .58 * veins));
    float cosine = max(0., dot(ray, wall));
    float reflectionAtWall = fresnel(cosine, index);
    vec3 red = refract(ray, -wall, index - (natural ? .026 : .067));
    vec3 green = refract(ray, -wall, index);
    vec3 blue = refract(ray, -wall, index + (natural ? .033 : .086));
    vec3 leaks = vec3(dot(red, red), dot(green, green), dot(blue, blue));
    vec3 transmitted = vec3(0.);
    if (leaks.r > .1) transmitted.r = environment(red).r;
    if (leaks.g > .1) transmitted.g = environment(green).g;
    if (leaks.b > .1) transmitted.b = environment(blue).b;
    color += energy * (1. - reflectionAtWall) * transmitted;
    energy *= 1. - (1. - reflectionAtWall) * leaks;
    ray = reflect(ray, wall);
    point += ray * .00025;
  }
  color += energy * environment(ray) * (natural ? .036 : .15);
  if (natural) {
    float faceLight = .28 + .72 * max(0., dot(turn * normal, vec3(-.47, -.62, .63)));
    color += vec3(.16, .013, .009) * (.24 + veins * veins) * faceLight;
  }

  vec3 mapped = pow(1. - exp(-max(vec3(0.), color) * 1.14), vec3(.54));
  fragment = vec4(mapped * opacity, opacity);
}`;

function compile(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (gl.getShaderParameter(shader, gl.COMPILE_STATUS)) return shader;
  const message = gl.getShaderInfoLog(shader);
  gl.deleteShader(shader);
  throw new Error(message);
}

function program(gl) {
  const result = gl.createProgram();
  const vertex = compile(gl, gl.VERTEX_SHADER, vertexShader);
  const fragment = compile(gl, gl.FRAGMENT_SHADER, fragmentShader);
  gl.attachShader(result, vertex);
  gl.attachShader(result, fragment);
  gl.linkProgram(result);
  gl.deleteShader(vertex);
  gl.deleteShader(fragment);
  if (gl.getProgramParameter(result, gl.LINK_STATUS)) return result;
  const message = gl.getProgramInfoLog(result);
  gl.deleteProgram(result);
  throw new Error(message);
}

function upload(gl, model) {
  const array = gl.createVertexArray();
  const buffer = gl.createBuffer();
  gl.bindVertexArray(array);
  gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
  const triangles = model.faces.flatMap(({ids, normal}) =>
    ids.flatMap(id => [...model.vertices[id], ...normal]));
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(triangles), gl.STATIC_DRAW);
  for (let attribute = 0; attribute < 2; attribute++) {
    gl.enableVertexAttribArray(attribute);
    gl.vertexAttribPointer(attribute, 3, gl.FLOAT, false, 24, attribute * 12);
  }
  return {array, count: triangles.length / 6, planes: new Float32Array(model.planes.flat())};
}

export function createGemRenderer(canvas) {
  const gl = canvas.getContext('webgl2', {alpha: true, antialias: true});
  if (!gl) return null;
  let shader;
  try {
    shader = program(gl);
  } catch (error) {
    console.warn('Rutile optics could not start. Using Canvas rendering.', error);
    return null;
  }
  const lab = upload(gl, labGem);
  const raw = upload(gl, naturalGem);
  const uniforms = Object.fromEntries(
    ['turn', 'center', 'zoom', 'distanceToGem', 'eye', 'planes', 'planeCount', 'natural', 'opacity']
      .map(name => [name, gl.getUniformLocation(shader, name)])
  );
  const debug = gl.getExtension('WEBGL_debug_renderer_info');
  const software = debug && /swiftshader|llvmpipe|software|warp/i.test(gl.getParameter(debug.UNMASKED_RENDERER_WEBGL));
  gl.useProgram(shader);
  gl.enable(gl.DEPTH_TEST);
  gl.enable(gl.CULL_FACE);
  gl.frontFace(gl.CW);
  gl.clearColor(0, 0, 0, 0);
  const clearBuffer = () => gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
  let activeModel;
  let painted = false;
  let pendingFrame = null;

  function releaseFrame() {
    if (pendingFrame) gl.deleteSync(pendingFrame);
    pendingFrame = null;
  }

  return {
    get available() { return !gl.isContextLost(); },
    resize(width, height, closeup, diving) {
      const budget = diving ? (software ? 100_000 : 340_000) :
        (software ? (closeup ? 380_000 : 220_000) : (closeup ? 1_100_000 : 650_000));
      const ratio = Math.min(window.devicePixelRatio || 1, Math.sqrt(budget / (width * height)));
      const pixelsWide = Math.max(1, Math.round(width * ratio));
      const pixelsHigh = Math.max(1, Math.round(height * ratio));
      if (canvas.width !== pixelsWide || canvas.height !== pixelsHigh) {
        releaseFrame();
        canvas.width = pixelsWide;
        canvas.height = pixelsHigh;
        painted = false;
      }
      gl.viewport(0, 0, canvas.width, canvas.height);
    },
    readyForFrame() {
      if (!pendingFrame) return true;
      if (gl.clientWaitSync(pendingFrame, 0, 0) === gl.TIMEOUT_EXPIRED) return false;
      releaseFrame();
      return true;
    },
    clear() {
      if (!painted) return;
      releaseFrame();
      clearBuffer();
      painted = false;
    },
    draw(turn, width, height, unit, pose, natural, trackCompletion) {
      clearBuffer();
      painted = true;
      const model = natural ? raw : lab;
      if (activeModel !== model) {
        gl.uniform4fv(uniforms.planes, model.planes);
        gl.uniform1i(uniforms.planeCount, model.planes.length / 4);
        gl.uniform1i(uniforms.natural, natural);
        gl.bindVertexArray(model.array);
        activeModel = model;
      }
      const {cx, cy, scale, distance, gem} = pose;
      const x = turn([1, 0, 0]), y = turn([0, 1, 0]), z = turn([0, 0, 1]);
      const focal = 2 * unit * scale * distance;
      gl.uniformMatrix3fv(uniforms.turn, false, [...x, ...y, ...z]);
      gl.uniform2f(uniforms.center, cx * 2 - 1, 1 - cy * 2);
      gl.uniform2f(uniforms.zoom, focal / width, -focal / height);
      gl.uniform1f(uniforms.distanceToGem, distance);
      gl.uniform3f(uniforms.eye, x[2] * distance, y[2] * distance, z[2] * distance);
      gl.uniform1f(uniforms.opacity, gem);
      gl.drawArrays(gl.TRIANGLES, 0, model.count);
      if (trackCompletion) {
        pendingFrame = gl.fenceSync(gl.SYNC_GPU_COMMANDS_COMPLETE, 0);
        gl.flush();
      } else {
        releaseFrame();
      }
    },
  };
}
