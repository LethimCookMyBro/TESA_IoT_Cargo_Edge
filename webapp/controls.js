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
