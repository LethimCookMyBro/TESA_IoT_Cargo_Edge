/**
 * The control contract of the CargoShield operator page, kept free of DOM and transport so it can be
 * checked against the Python engine. `tests/test_webapp_controls.py` feeds every payload below into
 * `CargoMqttService.handle_command` and asserts the engine accepts it.
 */

export const COMMANDS = {
  start: () => ({ action: 'start' }),
  pause: () => ({ action: 'pause' }),
  reset: () => ({ action: 'reset' }),
  // One button, two jobs: resume from pause and clear a latched safe stop. There is no separate resume.
  manual_resume: () => ({ action: 'manual_resume' }),
  set_cargo: (cargoType) => ({ action: 'set_cargo', cargo_type: cargoType }),
  set_mission: (pickup, destination) => ({ action: 'set_mission', pickup, destination }),
  set_obstacle: (distance) => ({ action: 'set_obstacle', distance: Number(distance) }),
  clear_obstacle: () => ({ action: 'clear_obstacle' }),
};

export const CARGO_TYPES = ['standard', 'fragile'];
export const ZONES = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2'];

/** Verified leaf paths of `cargoshield.state.v1`; see visual-flow/CARGOSHIELD_SENSOR_STUDIO_FLOW_BUILD.md. */
export const DISPLAY_PATHS = {
  status: 'status',
  cargo_type: 'cargo_type',
  obstacle_distance: 'obstacle_distance',
  label: 'last.label',
  confidence: 'last.confidence',
  risk: 'last.risk',
  action: 'last.decision.action',
  speed_ratio: 'last.decision.speed_ratio',
  reason: 'last.decision.reason',
  zone: 'last.zone',
  progress: 'last.progress',
  route_nodes: 'route.nodes',
  route_reason: 'route.reason',
};

export function read(state, path) {
  let value = state;
  for (const key of path.split('.')) {
    if (!value || typeof value !== 'object' || !(key in value)) return undefined;
    value = value[key];
  }
  return value;
}

export const topics = (deviceId) => ({
  command: `cargoshield/${deviceId}/command`,
  state: `cargoshield/${deviceId}/state`,
});

/** Amber for a non-fatal hold, red for a stop or error, green while under way. */
export function statusTone(status) {
  if (status === 'SAFE_STOPPED' || status === 'ERROR') return 'stop';
  if (status === 'HOLDING' || status === 'PAUSED') return 'hold';
  if (status === 'MOVING' || status === 'SLOWING') return 'go';
  return 'idle';
}

/* ------------------------------------------------------------------ *
 * Visualization contract. The 3D scene renders published state only;
 * nothing below decides anything — the Python engine already did.
 * `tests/test_webapp_visual.py` pins these against the engine.
 * ------------------------------------------------------------------ */

/** Mirrors `cargo.decision_engine.CargoPolicy`, so the scene colours match the engine's regions. */
export const OBSTACLE_POLICY = { stop_distance: 30.0, warning_distance: 80.0 };

/** Which visual band a distance falls in. Colour only; the engine still owns the decision. */
export function obstacleTone(distance) {
  if (distance === null || distance === undefined || Number.isNaN(Number(distance))) return 'none';
  const value = Number(distance);
  if (value <= OBSTACLE_POLICY.stop_distance) return 'stop';
  if (value <= OBSTACLE_POLICY.warning_distance) return 'warn';
  return 'clear';
}

/** Floor plan of the demo map, in metres. Laid out so every DEMO_GRAPH edge is a straight aisle. */
export const ZONE_POSITIONS = {
  A1: [-8, -9], A2: [8, -9],
  B1: [-8, 0], B2: [8, 0],
  C1: [-8, 9], C2: [8, 9],
};

/** The undirected aisles of DEMO_GRAPH, drawn as the warehouse's travel lanes. */
export const DEMO_EDGES = [
  ['A1', 'A2'], ['A1', 'B1'], ['A2', 'B2'],
  ['B1', 'C1'], ['B2', 'C2'], ['C1', 'C2'],
];

/** The only statuses under which the robot may be shown moving. */
export const MOVING_STATUSES = new Set(['MOVING', 'SLOWING']);

/**
 * How the scene is allowed to animate the robot for a state.
 * `speed` is the engine's own speed ratio, so SLOW_DOWN visibly slows the model down.
 */
export function motion(state) {
  const status = read(state, 'status');
  const ratio = read(state, 'last.decision.speed_ratio');
  const halted = status === 'SAFE_STOPPED' || status === 'ERROR';
  if (halted || !MOVING_STATUSES.has(status)) return { animate: false, speed: 0, halted };
  const speed = typeof ratio === 'number' ? Math.min(1, Math.max(0, ratio)) : 1;
  return { animate: speed > 0, speed, halted: false };
}

/**
 * Where along `nodes` the robot is, as a 0..1 fraction, from the engine's own zone and progress.
 * The reported zone is authoritative; progress only refines the position between it and the next
 * node, so the robot is never drawn ahead of a node the engine has not reported reaching.
 * Returns null when there is no route to walk.
 */
export function routePosition(nodes, zone, progress) {
  if (!Array.isArray(nodes) || nodes.length === 0) return null;
  const span = Math.max(1, nodes.length - 1);
  const index = nodes.indexOf(zone);
  const atZone = index < 0 ? 0 : index / span;
  const next = index < 0 ? 1 : Math.min(1, (index + 1) / span);
  if (typeof progress !== 'number' || !Number.isFinite(progress)) return atZone;
  return Math.min(next, Math.max(atZone, Math.min(1, Math.max(0, progress))));
}

/** Floor tint per Surface AI class from `models/label_mapping.json`; null for anything unseen. */
export const SURFACE_TINTS = {
  hard_tiles_large_space: '#4a6b8a', soft_pvc: '#7a5b8f', soft_tiles: '#5f7f92',
  fine_concrete: '#6b6f74', concrete: '#585c61', hard_tiles: '#3f6f7a',
  carpet: '#8a5a4a', tiled: '#4f7a6b', wood: '#8a6b3f',
};
export const surfaceTint = (label) => SURFACE_TINTS[label] ?? null;
