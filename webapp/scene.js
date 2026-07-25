/**
 * Procedural warehouse view of the published mission state. Rendering only: every value drawn here
 * comes from a `cargoshield.state.v1` message, and nothing in this file decides anything. When the
 * engine has not published a value the scene leaves the corresponding object hidden rather than
 * inventing one.
 */

import * as THREE from 'three';
import { OrbitControls } from './vendor/three/OrbitControls.js';
import {
  ZONE_POSITIONS, DEMO_EDGES, motion, routePosition, obstacleTone, surfaceTint, read, statusTone,
} from './controls.js';

const COLORS = {
  floor: 0x14181d, grid: 0x1f2a33, wall: 0x1a2027, rack: 0x3a4550, pallet: 0x6d5a3c,
  lane: 0x27333d, travelled: 0x22c55e, current: 0x38bdf8, remaining: 0x3b4c5e,
  zone: 0x2b3540, robot: 0x2f3a45, skirt: 0xd9a520, wheel: 0x15191d,
  cargoStandard: 0x8aa2b8, cargoFragile: 0xffb445, strap: 0xef4444,
  go: 0x22c55e, hold: 0xf59e0b, stop: 0xef4444, idle: 0x64748b,
  obstacleWarn: 0xfacc15, obstacleStop: 0xef4444, obstacleClear: 0x94a3b8,
};

// Centimetres of simulated obstacle distance per metre of scene. The slider tops out at 200 cm,
// which puts the marker 10 m ahead; the engine's 30 cm stop region lands at 1.5 m.
const CM_PER_METRE = 20;
const ZONE_RADIUS = 2.8;

const disposeTree = (root) => root.traverse((node) => {
  node.geometry?.dispose();
  for (const material of [node.material].flat().filter(Boolean)) {
    for (const value of Object.values(material)) value?.isTexture && value.dispose();
    material.dispose();
  }
});

/** Text drawn to a canvas: no font file to ship and no glyph geometry to build. */
function makeLabel(width = 256, height = 128) {
  const canvas = Object.assign(document.createElement('canvas'), { width, height });
  const context = canvas.getContext('2d');
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false }));
  let painted = '';
  const draw = (title, subtitle, tint) => {
    const key = `${title}|${subtitle}|${tint}`;
    if (key === painted) return;
    painted = key;
    context.clearRect(0, 0, width, height);
    context.textAlign = 'center';
    context.fillStyle = tint;
    context.font = `700 ${height * 0.42}px system-ui, sans-serif`;
    context.fillText(title, width / 2, height * 0.44);
    if (subtitle) {
      context.fillStyle = 'rgba(226,232,240,0.85)';
      context.font = `500 ${height * 0.2}px system-ui, sans-serif`;
      context.fillText(subtitle, width / 2, height * 0.78);
    }
    texture.needsUpdate = true;
  };
  return { sprite, draw };
}

function buildRack(shelves = 3) {
  const rack = new THREE.Group();
  const frame = new THREE.MeshStandardMaterial({ color: COLORS.rack, roughness: 0.75, metalness: 0.35 });
  const upright = new THREE.BoxGeometry(0.2, 4.2, 0.2);
  for (const x of [-1.6, 1.6]) for (const z of [-0.7, 0.7]) {
    const post = new THREE.Mesh(upright, frame);
    post.position.set(x, 2.1, z);
    post.castShadow = true;
    rack.add(post);
  }
  const shelf = new THREE.BoxGeometry(3.4, 0.12, 1.6);
  const pallet = new THREE.BoxGeometry(1.2, 0.9, 1.1);
  const palletMaterial = new THREE.MeshStandardMaterial({ color: COLORS.pallet, roughness: 0.9 });
  for (let level = 0; level < shelves; level += 1) {
    const board = new THREE.Mesh(shelf, frame);
    board.position.y = 0.6 + level * 1.6;
    board.castShadow = board.receiveShadow = true;
    rack.add(board);
    // Deterministic gaps, so the warehouse looks stocked without pretending to be inventory data.
    for (const [slot, x] of [[0, -0.9], [1, 0.9]]) {
      if ((level + slot) % 3 === 2) continue;
      const box = new THREE.Mesh(pallet, palletMaterial);
      box.position.set(x, 1.11 + level * 1.6, 0);
      box.castShadow = true;
      rack.add(box);
    }
  }
  return rack;
}

function buildRobot() {
  const robot = new THREE.Group();
  const body = new THREE.MeshStandardMaterial({ color: COLORS.robot, roughness: 0.5, metalness: 0.6 });

  const skirt = new THREE.Mesh(new THREE.BoxGeometry(2.7, 0.3, 3.7), new THREE.MeshStandardMaterial({ color: COLORS.skirt, roughness: 0.6 }));
  skirt.position.y = 0.42;
  const chassis = new THREE.Mesh(new THREE.BoxGeometry(2.4, 0.8, 3.4), body);
  chassis.position.y = 0.95;
  const deck = new THREE.Mesh(new THREE.BoxGeometry(2.0, 0.2, 2.6), body);
  deck.position.y = 1.45;
  for (const mesh of [skirt, chassis, deck]) { mesh.castShadow = true; robot.add(mesh); }

  const wheelGeometry = new THREE.CylinderGeometry(0.45, 0.45, 0.34, 18);
  const wheelMaterial = new THREE.MeshStandardMaterial({ color: COLORS.wheel, roughness: 0.95 });
  const wheels = [];
  for (const x of [-1.25, 1.25]) for (const z of [-1.15, 1.15]) {
    const wheel = new THREE.Mesh(wheelGeometry, wheelMaterial);
    wheel.rotation.z = Math.PI / 2;
    wheel.position.set(x, 0.45, z);
    wheel.castShadow = true;
    robot.add(wheel);
    wheels.push(wheel);
  }

  // Front sensor head: the lidar puck is decoration, the beacon carries the engine's status colour.
  const puck = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.34, 0.22, 20), new THREE.MeshStandardMaterial({ color: 0x0f1418, roughness: 0.4 }));
  puck.position.set(0, 1.66, 1.25);
  const mast = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, 1.0, 10), body);
  mast.position.set(-0.9, 2.05, -1.2);
  const beaconMaterial = new THREE.MeshStandardMaterial({ color: COLORS.idle, emissive: COLORS.idle, emissiveIntensity: 1.2, roughness: 0.3 });
  const beacon = new THREE.Mesh(new THREE.SphereGeometry(0.24, 18, 14), beaconMaterial);
  beacon.position.set(-0.9, 2.62, -1.2);
  const beaconLight = new THREE.PointLight(COLORS.idle, 0, 9, 2);
  beaconLight.position.copy(beacon.position);
  robot.add(puck, mast, beacon, beaconLight);

  const cargoMaterial = new THREE.MeshStandardMaterial({ color: COLORS.cargoStandard, roughness: 0.6, metalness: 0.25 });
  const cargo = new THREE.Mesh(new THREE.BoxGeometry(1.9, 1.5, 2.3), cargoMaterial);
  cargo.position.y = 2.3;
  cargo.castShadow = true;
  const cargoEdges = new THREE.LineSegments(new THREE.EdgesGeometry(cargo.geometry), new THREE.LineBasicMaterial({ color: 0x0b0f13 }));
  cargoEdges.position.copy(cargo.position);
  // Only fragile cargo is strapped, so the two cargo types are told apart from any camera angle.
  const strap = new THREE.Mesh(new THREE.BoxGeometry(2.0, 0.22, 2.4), new THREE.MeshStandardMaterial({ color: COLORS.strap, roughness: 0.5 }));
  strap.position.y = 2.3;
  strap.visible = false;
  const cargoLabel = makeLabel(256, 96);
  cargoLabel.sprite.scale.set(3.2, 1.2, 1);
  cargoLabel.sprite.position.set(0, 3.6, 0);
  robot.add(cargo, cargoEdges, strap, cargoLabel.sprite);

  const perimeter = new THREE.Mesh(
    new THREE.RingGeometry(3.0, 3.5, 48),
    new THREE.MeshBasicMaterial({ color: COLORS.stop, transparent: true, opacity: 0.6, side: THREE.DoubleSide, depthWrite: false }),
  );
  perimeter.rotation.x = -Math.PI / 2;
  perimeter.position.y = 0.06;
  perimeter.visible = false;
  robot.add(perimeter);

  return { robot, wheels, beacon, beaconLight, cargoMaterial, strap, cargoLabel, perimeter };
}

function buildObstacle() {
  const group = new THREE.Group();
  const material = new THREE.MeshStandardMaterial({ color: COLORS.obstacleClear, roughness: 0.7, emissive: 0x000000 });
  const drum = new THREE.Mesh(new THREE.CylinderGeometry(0.55, 0.75, 1.1, 20), material);
  drum.position.y = 0.55;
  drum.castShadow = true;
  const cone = new THREE.Mesh(new THREE.ConeGeometry(0.55, 0.9, 20), material);
  cone.position.y = 1.55;
  const stripe = new THREE.Mesh(new THREE.CylinderGeometry(0.68, 0.68, 0.22, 20), new THREE.MeshStandardMaterial({ color: 0x11161b, roughness: 0.8 }));
  stripe.position.y = 0.72;
  const zone = new THREE.Mesh(
    new THREE.RingGeometry(1.2, 1.7, 40),
    new THREE.MeshBasicMaterial({ color: COLORS.obstacleStop, transparent: true, opacity: 0.55, side: THREE.DoubleSide, depthWrite: false }),
  );
  zone.rotation.x = -Math.PI / 2;
  zone.position.y = 0.05;
  zone.visible = false;
  const label = makeLabel(256, 96);
  label.sprite.scale.set(3.0, 1.1, 1);
  label.sprite.position.set(0, 2.7, 0);
  group.add(drum, cone, stripe, zone, label.sprite);
  group.visible = false;
  return { group, material, zone, label };
}

/**
 * @returns a scene handle, or null when the browser cannot give us a WebGL context. The caller keeps
 * the 2D panels either way.
 */
export function createScene(canvas, { reducedMotion = false } = {}) {
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
  } catch (error) {
    console.warn('CargoShield: WebGL unavailable, falling back to panels only', error);
    return null;
  }
  if (!renderer.getContext()) return null;

  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0a0d11);
  scene.fog = new THREE.Fog(0x0a0d11, 62, 132);

  const camera = new THREE.PerspectiveCamera(48, 1, 0.5, 220);
  // Framed so the whole demo map, both rack walls and the zone labels fit at 16:9 and on a laptop.
  const HOME = { position: new THREE.Vector3(28, 31, 40), target: new THREE.Vector3(0, 1.5, 0) };
  camera.position.copy(HOME.position);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minDistance = 12;
  controls.maxDistance = 90;
  controls.maxPolarAngle = Math.PI * 0.48;
  controls.target.copy(HOME.target);

  scene.add(new THREE.HemisphereLight(0x9fc6ff, 0x141a20, 1.0));
  const key = new THREE.DirectionalLight(0xf2f6ff, 1.6);
  key.position.set(22, 34, 16);
  key.castShadow = true;
  key.shadow.mapSize.set(1024, 1024);
  key.shadow.camera.near = 5;
  key.shadow.camera.far = 90;
  Object.assign(key.shadow.camera, { left: -32, right: 32, top: 30, bottom: -30 });
  key.shadow.camera.updateProjectionMatrix();
  key.shadow.bias = -0.0008;
  scene.add(key);
  const fill = new THREE.DirectionalLight(0x5f7fa8, 0.35);
  fill.position.set(-20, 16, -22);
  scene.add(fill);

  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(56, 46),
    new THREE.MeshStandardMaterial({ color: COLORS.floor, roughness: 0.95, metalness: 0.05 }),
  );
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  const grid = new THREE.GridHelper(56, 28, COLORS.grid, COLORS.grid);
  grid.position.y = 0.01;
  scene.add(floor, grid);

  const wallMaterial = new THREE.MeshStandardMaterial({ color: COLORS.wall, roughness: 1 });
  for (const [w, h, d, x, z] of [[56, 3, 0.6, 0, -23], [56, 3, 0.6, 0, 23], [0.6, 3, 46, -28, 0], [0.6, 3, 46, 28, 0]]) {
    const wall = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), wallMaterial);
    wall.position.set(x, 1.5, z);
    wall.receiveShadow = true;
    scene.add(wall);
  }

  for (const [x, z, rotation] of [[-21, -12, 0], [-21, 0, 0], [-21, 12, 0], [21, -12, 0], [21, 0, 0], [21, 12, 0], [0, -18, Math.PI / 2], [0, 18, Math.PI / 2]]) {
    const rack = buildRack();
    rack.position.set(x, 0, z);
    rack.rotation.y = rotation;
    scene.add(rack);
  }

  // Faint lanes for every DEMO_GRAPH edge; the active route is drawn brighter on top of them.
  const laneMaterial = new THREE.MeshBasicMaterial({ color: COLORS.lane, transparent: true, opacity: 0.5 });
  const segmentGeometry = new THREE.PlaneGeometry(1, 1);
  const placeSegment = (mesh, from, to, width) => {
    const [ax, az] = ZONE_POSITIONS[from];
    const [bx, bz] = ZONE_POSITIONS[to];
    const length = Math.hypot(bx - ax, bz - az);
    mesh.position.set((ax + bx) / 2, mesh.position.y, (az + bz) / 2);
    mesh.rotation.set(-Math.PI / 2, 0, -Math.atan2(bz - az, bx - ax));
    mesh.scale.set(length, width, 1);
  };
  for (const [from, to] of DEMO_EDGES) {
    const lane = new THREE.Mesh(segmentGeometry, laneMaterial);
    lane.position.y = 0.02;
    placeSegment(lane, from, to, 1.1);
    scene.add(lane);
  }

  // One ribbon per possible route hop, recoloured as travelled / current / remaining.
  const MAX_HOPS = 8;
  const routeSegments = Array.from({ length: MAX_HOPS }, () => {
    const mesh = new THREE.Mesh(segmentGeometry, new THREE.MeshBasicMaterial({ color: COLORS.remaining, transparent: true, opacity: 0.9 }));
    mesh.position.y = 0.035;
    mesh.visible = false;
    scene.add(mesh);
    return mesh;
  });

  const zoneMarkers = new Map();
  for (const [name, [x, z]] of Object.entries(ZONE_POSITIONS)) {
    const group = new THREE.Group();
    group.position.set(x, 0, z);
    const pad = new THREE.Mesh(
      new THREE.CircleGeometry(ZONE_RADIUS, 40),
      new THREE.MeshStandardMaterial({ color: COLORS.zone, roughness: 0.85 }),
    );
    pad.rotation.x = -Math.PI / 2;
    pad.position.y = 0.015;
    pad.receiveShadow = true;
    // Heat overlay: hidden until the engine has actually observed risk in this zone.
    const heat = new THREE.Mesh(
      new THREE.RingGeometry(ZONE_RADIUS * 0.72, ZONE_RADIUS, 40),
      new THREE.MeshBasicMaterial({ color: COLORS.idle, transparent: true, opacity: 0.0, side: THREE.DoubleSide, depthWrite: false }),
    );
    heat.rotation.x = -Math.PI / 2;
    heat.position.y = 0.045;
    const active = new THREE.Mesh(
      new THREE.RingGeometry(ZONE_RADIUS * 1.06, ZONE_RADIUS * 1.24, 40),
      new THREE.MeshBasicMaterial({ color: COLORS.current, transparent: true, opacity: 0.9, side: THREE.DoubleSide, depthWrite: false }),
    );
    active.rotation.x = -Math.PI / 2;
    active.position.y = 0.05;
    active.visible = false;
    const label = makeLabel(256, 128);
    label.sprite.scale.set(4.2, 2.1, 1);
    label.sprite.position.y = 2.6;
    group.add(pad, heat, active, label.sprite);
    scene.add(group);
    zoneMarkers.set(name, { pad, heat, active, label });
  }

  const { robot, wheels, beacon, beaconLight, cargoMaterial, strap, cargoLabel, perimeter } = buildRobot();
  scene.add(robot);
  const obstacle = buildObstacle();
  scene.add(obstacle.group);

  /* ---------------- state the animation loop reads ---------------- */

  const visual = { fraction: 0, heading: 0 };
  let target = { fraction: 0, nodes: [], speed: 0, animate: false, halted: false };
  let latest = null;
  let missionKey = '';
  let frames = 0;
  let fpsWindow = performance.now();
  let fps = 0;
  const onFps = new Set();

  const pointAt = (nodes, fraction) => {
    if (!nodes.length) return new THREE.Vector3(0, 0, 0);
    if (nodes.length === 1) {
      const [x, z] = ZONE_POSITIONS[nodes[0]] ?? [0, 0];
      return new THREE.Vector3(x, 0, z);
    }
    const span = nodes.length - 1;
    const scaled = Math.min(span - 1e-6, Math.max(0, fraction * span));
    const index = Math.floor(scaled);
    const t = scaled - index;
    const [ax, az] = ZONE_POSITIONS[nodes[index]] ?? [0, 0];
    const [bx, bz] = ZONE_POSITIONS[nodes[index + 1]] ?? [ax, az];
    return new THREE.Vector3(ax + (bx - ax) * t, 0, az + (bz - az) * t);
  };

  const headingAt = (nodes, fraction) => {
    if (nodes.length < 2) return visual.heading;
    const ahead = pointAt(nodes, Math.min(1, fraction + 0.02));
    const behind = pointAt(nodes, Math.max(0, fraction - 0.02));
    const dx = ahead.x - behind.x;
    const dz = ahead.z - behind.z;
    return dx === 0 && dz === 0 ? visual.heading : Math.atan2(dx, dz);
  };

  function applyRoute(nodes, fraction) {
    for (const [index, mesh] of routeSegments.entries()) {
      const from = nodes[index];
      const to = nodes[index + 1];
      mesh.visible = Boolean(from && to);
      if (!mesh.visible) continue;
      placeSegment(mesh, from, to, 1.5);
      const span = nodes.length - 1;
      const start = index / span;
      const end = (index + 1) / span;
      // Three distinct colours: behind the robot, the hop it is on, and the hops still to walk.
      mesh.material.color.setHex(fraction >= end - 1e-6 ? COLORS.travelled : fraction > start ? COLORS.current : COLORS.remaining);
    }
  }

  function applyZones(state, currentZone) {
    const riskMap = read(state, 'risk_map') ?? {};
    for (const [name, marker] of zoneMarkers) {
      const entry = riskMap[name];
      const score = typeof entry?.score === 'number' ? entry.score : null;
      const tint = surfaceTint(entry?.surface);
      marker.pad.material.color.setHex(tint ? Number.parseInt(tint.slice(1), 16) : COLORS.zone);
      if (score === null) {
        marker.heat.material.opacity = 0;
        marker.label.draw(name, 'risk N/A', '#cbd5e1');
      } else {
        // Green through red by the engine's own averaged zone score; no scale is invented.
        marker.heat.material.color.setHSL((1 - Math.min(1, Math.max(0, score))) * 0.33, 0.85, 0.5);
        marker.heat.material.opacity = 0.35 + Math.min(1, score) * 0.5;
        marker.label.draw(name, `risk ${(score * 100).toFixed(0)}%`, '#e2e8f0');
      }
      marker.active.visible = name === currentZone;
    }
  }

  /** Feed a published state message into the scene. */
  function apply(state) {
    latest = state ?? null;
    const nodes = (read(state, 'route.nodes') ?? []).filter((node) => node in ZONE_POSITIONS);
    const zone = read(state, 'last.zone');
    const progress = read(state, 'last.progress');
    const status = read(state, 'status');
    const fraction = routePosition(nodes, zone, progress) ?? 0;
    const move = motion(state);

    // A different route, or a run that restarted from the top, is a new mission: put the model back
    // at the start instead of sliding it across the warehouse from wherever the last run ended.
    const key = `${nodes.join('>')}|${status === 'IDLE' ? 'idle' : 'run'}`;
    const restarted = key !== missionKey || (typeof progress === 'number' && progress < visual.fraction - 0.34);
    missionKey = key;
    if (restarted || status === 'IDLE') {
      visual.fraction = status === 'IDLE' ? 0 : fraction;
      visual.heading = headingAt(nodes, visual.fraction);
    }
    target = { fraction, nodes, speed: move.speed, animate: move.animate, halted: move.halted };

    applyRoute(nodes, visual.fraction);
    applyZones(state, zone);

    const tone = statusTone(status);
    const toneColor = COLORS[tone] ?? COLORS.idle;
    beacon.material.color.setHex(toneColor);
    beacon.material.emissive.setHex(toneColor);
    beaconLight.color.setHex(toneColor);
    beaconLight.intensity = tone === 'idle' ? 0.6 : 2.2;
    perimeter.visible = move.halted;

    const fragile = read(state, 'cargo_type') === 'fragile';
    cargoMaterial.color.setHex(fragile ? COLORS.cargoFragile : COLORS.cargoStandard);
    cargoMaterial.transparent = fragile;
    cargoMaterial.opacity = fragile ? 0.72 : 1;
    cargoMaterial.needsUpdate = true;
    strap.visible = fragile;
    cargoLabel.draw(fragile ? 'FRAGILE' : 'STANDARD', '', fragile ? '#ffb445' : '#cbd5e1');

    const distance = read(state, 'obstacle_distance');
    const obstacleState = obstacleTone(distance);
    obstacle.group.visible = obstacleState !== 'none';
    if (obstacle.group.visible) {
      const color = obstacleState === 'stop' ? COLORS.obstacleStop : obstacleState === 'warn' ? COLORS.obstacleWarn : COLORS.obstacleClear;
      obstacle.material.color.setHex(color);
      obstacle.material.emissive.setHex(obstacleState === 'clear' ? 0x000000 : color);
      obstacle.material.emissiveIntensity = 0.45;
      obstacle.zone.visible = obstacleState === 'stop';
      obstacle.label.draw(`${Number(distance)} cm`, obstacleState === 'stop' ? 'SAFE STOP REGION' : obstacleState === 'warn' ? 'SLOW REGION' : 'clear', color === COLORS.obstacleClear ? '#cbd5e1' : `#${color.toString(16).padStart(6, '0')}`);
    }
  }

  /* ---------------- render loop ---------------- */

  const clock = new THREE.Clock();
  let running = true;
  let raf = 0;

  function frame() {
    if (!running) return;
    raf = requestAnimationFrame(frame);
    const dt = Math.min(0.05, clock.getDelta());

    // Visual smoothing only, and only when the engine says the robot may move. A halted, paused or
    // holding mission freezes exactly where the last published state put it.
    let moved = 0;
    if (target.animate && visual.fraction !== target.fraction) {
      const span = Math.max(1, target.nodes.length - 1);
      const step = (dt * target.speed * 1.4) / span;
      const delta = target.fraction - visual.fraction;
      moved = Math.min(Math.abs(delta), step) * Math.sign(delta);
      visual.fraction += moved;
      applyRoute(target.nodes, visual.fraction);
    } else if (!target.animate && target.nodes.length && Math.abs(target.fraction - visual.fraction) > 0.5) {
      // A finished or reset run snaps rather than pretending to drive there.
      visual.fraction = target.fraction;
      applyRoute(target.nodes, visual.fraction);
    }

    if (target.nodes.length) {
      const point = pointAt(target.nodes, visual.fraction);
      const travelled = Math.hypot(point.x - robot.position.x, point.z - robot.position.z);
      robot.position.set(point.x, 0, point.z);
      const heading = headingAt(target.nodes, visual.fraction);
      visual.heading += (heading - visual.heading) * Math.min(1, dt * 6);
      robot.rotation.y = visual.heading;
      // Wheels turn with the metres actually covered, so they stop dead when the mission does.
      if (moved !== 0) for (const wheel of wheels) wheel.rotation.x += travelled / 0.45;
    }

    const distance = read(latest, 'obstacle_distance');
    if (obstacle.group.visible && Number.isFinite(Number(distance))) {
      const ahead = Math.max(0.8, Number(distance) / CM_PER_METRE);
      obstacle.group.position.set(
        robot.position.x + Math.sin(visual.heading) * (ahead + 1.7),
        0,
        robot.position.z + Math.cos(visual.heading) * (ahead + 1.7),
      );
    }

    if (!reducedMotion) {
      const pulse = 0.45 + Math.abs(Math.sin(clock.elapsedTime * 3.2)) * 0.35;
      if (perimeter.visible) perimeter.material.opacity = pulse;
      if (obstacle.zone.visible) obstacle.zone.material.opacity = pulse;
      beacon.material.emissiveIntensity = target.halted ? 0.7 + pulse : 1.3;
    }

    controls.update();
    renderer.render(scene, camera);

    frames += 1;
    const now = performance.now();
    if (now - fpsWindow >= 1000) {
      fps = Math.round((frames * 1000) / (now - fpsWindow));
      frames = 0;
      fpsWindow = now;
      for (const handler of onFps) handler(fps);
    }
  }

  function resize() {
    const width = canvas.clientWidth || 1;
    const height = canvas.clientHeight || 1;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }

  const observer = new ResizeObserver(resize);
  observer.observe(canvas);
  resize();
  raf = requestAnimationFrame(frame);

  return {
    apply,
    resetCamera() {
      camera.position.copy(HOME.position);
      controls.target.copy(HOME.target);
      controls.update();
    },
    onFps(handler) { onFps.add(handler); return () => onFps.delete(handler); },
    dispose() {
      running = false;
      cancelAnimationFrame(raf);
      observer.disconnect();
      controls.dispose();
      disposeTree(scene);
      renderer.dispose();
    },
  };
}
