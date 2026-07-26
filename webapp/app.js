/**
 * Operator console wiring: MQTT in, commands out, published state onto the panels and the 3D scene.
 * The Python engine remains authoritative — this file renders what it publishes and never derives a
 * status, decision or inference of its own.
 */

import { LiveDataClient, DEFAULT_MQTT_WS_URL } from './live-data.browser.js';
import { createScene } from './scene.js';
import {
  COMMANDS, CARGO_TYPES, ZONES, DISPLAY_PATHS, read, topics, statusTone, obstacleTone,
} from './controls.js';

const params = new URLSearchParams(location.search);
const deviceId = params.get('device') ?? 'cargo-robot-01';
const url = params.get('url') ?? DEFAULT_MQTT_WS_URL;   // ws://127.0.0.1:8883
const topic = topics(deviceId);

const $ = (id) => document.getElementById(id);
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/* ---------------- 3D stage (optional) ---------------- */

const stage = createScene($('stage'), { reducedMotion });
if (stage) {
  $('reset-camera').addEventListener('click', () => stage.resetCamera());
  stage.onFps((value) => { $('fps').textContent = `${value} fps`; });
} else {
  $('stage').hidden = true;
  $('stage-fallback').hidden = false;
  $('reset-camera').disabled = true;
  $('fps').hidden = true;
}

/* ---------------- toasts ---------------- */

function toast(message, bad = false) {
  const node = document.createElement('div');
  node.className = bad ? 'toast bad' : 'toast';
  node.textContent = message;
  $('toasts').append(node);
  setTimeout(() => node.remove(), bad ? 6000 : 3000);
}

/* ---------------- controls ---------------- */

const CARGO_LABELS = { standard: 'สินค้าทั่วไป', fragile: 'สินค้าเปราะบาง' };
const SOURCE_PRESENTATION = {
  dataset: {
    label: 'DATASET REPLAY · validation split แยกจาก train/test · ไม่ใช่การวัดสด',
    progress: 'ความคืบหน้าการ Replay',
  },
  simulated: {
    label: 'SIMULATION · ข้อมูลสังเคราะห์ · ไม่ใช่การวัดสด',
    progress: 'ความคืบหน้าสถานการณ์จำลอง',
  },
  hardware: {
    label: 'LIVE HARDWARE · การวัดสดจากอุปกรณ์',
    progress: 'ความคืบหน้าภารกิจสด',
  },
};
$('cargo').append(...CARGO_TYPES.map((value) => new Option(`${CARGO_LABELS[value]} (${value})`, value)));
for (const select of [$('pickup'), $('destination')]) {
  select.append(...ZONES.map((value) => new Option(value, value)));
}
$('pickup').value = 'A1';
$('destination').value = 'C2';

// Unique per page instance: MQTT brokers evict an older session that reconnects with the same client
// id, so a second tab or a refresh would otherwise knock the first console off the broker.
const clientId = `cargoshield-console-${deviceId}-${Math.random().toString(36).slice(2, 8)}`;
const client = new LiveDataClient({ transport: 'mqtt', url, clientId });

const pending = new Set();
const sentAt = new Map();
// A demo is a live system: one accidental double-click must not queue two missions. Keyed on the
// payload, so changing pickup and destination in quick succession still sends both commands.
const MIN_REPEAT_MS = 400;
// Bounded retry across a transport reconnect. Three attempts 400 ms apart covers the observed
// WebSocket drop without ever queueing a command indefinitely.
const COMMAND_ATTEMPTS = 3;
const COMMAND_RETRY_MS = 400;

async function send(name, payload, button) {
  const key = JSON.stringify(payload);
  const now = performance.now();
  if (now - (sentAt.get(key) ?? -Infinity) < MIN_REPEAT_MS) return;
  sentAt.set(key, now);
  if (button) {
    button.dataset.busy = 'true';
    button.disabled = true;
    pending.add(button);
    // Cleared by the next published state; the timeout only covers a broker that never answers.
    setTimeout(() => release(button), 3000);
  }
  // A WebSocket that is reconnecting rejects the write ("already in CLOSING or CLOSED state") and
  // the operator's command is simply lost. Retry across the reconnect window before giving up:
  // pressing Stop must not silently do nothing because a ping was missed a moment earlier.
  for (let attempt = 0; attempt < COMMAND_ATTEMPTS; attempt += 1) {
    try {
      // Commands are sparse and must reach the broker; QoS 1 gives publish() a PUBACK to await.
      // State telemetry stays QoS 0 in the Python service.
      await client.publish(topic.command, payload, { qos: 1 });
      return;
    } catch (error) {
      if (attempt === COMMAND_ATTEMPTS - 1) {
        release(button);
        toast(`ส่งคำสั่งไม่สำเร็จ: ${error?.message ?? error}`, true);
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, COMMAND_RETRY_MS));
    }
  }
}

function release(button) {
  if (!button || !pending.has(button)) return;
  pending.delete(button);
  delete button.dataset.busy;
  button.disabled = false;
}

for (const button of document.querySelectorAll('button[data-cmd]')) {
  button.addEventListener('click', () => send(button.dataset.cmd, COMMANDS[button.dataset.cmd](), button));
}
$('cargo').addEventListener('change', (event) => send('set_cargo', COMMANDS.set_cargo(event.target.value)));
for (const id of ['pickup', 'destination']) {
  $(id).addEventListener('change', () => send('set_mission', COMMANDS.set_mission($('pickup').value, $('destination').value)));
}
const obstacleRange = $('obstacle');
const obstacleNumber = $('obstacle-value');

function obstacleValue() {
  const value = Number(obstacleNumber.value);
  if (!Number.isFinite(value) || value < 0 || value > 200) {
    obstacleNumber.reportValidity();
    return null;
  }
  return value;
}

obstacleRange.addEventListener('input', () => { obstacleNumber.value = obstacleRange.value; });
obstacleNumber.addEventListener('input', () => {
  const value = obstacleValue();
  if (value !== null) obstacleRange.value = String(value);
});
obstacleNumber.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') $('obstacle-send').click();
});
$('obstacle-send').addEventListener('click', (event) => {
  const value = obstacleValue();
  if (value !== null) send('set_obstacle', COMMANDS.set_obstacle(value), event.currentTarget);
});

/* ---------------- rendering ---------------- */

const NA = 'N/A';
const show = (value) => {
  if (value === undefined || value === null) return NA;
  if (Array.isArray(value)) return value.length ? value.join(' → ') : NA;
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(3);
  return String(value);
};

let lastStateAt = null;
let lastEventMs = 0;
// Counts states actually published by the engine. Exposed on #status so an automated check can
// tell "the engine answered and it is READY" apart from "it was already READY before I asked".
let statesRendered = 0;

function renderTimeline(events) {
  if (!Array.isArray(events)) return;
  const fresh = events.filter((event) => event.timestamp_ms > lastEventMs);
  if (!fresh.length) return;
  lastEventMs = fresh.at(-1).timestamp_ms;
  const list = $('timeline');
  for (const event of fresh) {
    const item = document.createElement('li');
    const time = document.createElement('time');
    time.textContent = new Date(event.timestamp_ms).toLocaleTimeString();
    const text = document.createElement('span');
    text.textContent = event.message;
    item.append(time, text);
    list.prepend(item);
  }
  // Bounded so a long demo cannot grow the DOM without limit.
  while (list.children.length > 60) list.lastElementChild.remove();
}

function renderRisk(riskMap) {
  const list = $('risk-list');
  const entries = Object.entries(riskMap ?? {});
  if (!entries.length) {
    list.innerHTML = '<li>no zone observed yet</li>';
    return;
  }
  list.replaceChildren(...entries.map(([zone, value]) => {
    const item = document.createElement('li');
    const score = Math.min(1, Math.max(0, Number(value?.score) || 0));
    const name = document.createElement('b');
    name.textContent = zone;
    const bar = document.createElement('span');
    bar.className = 'bar';
    const fill = document.createElement('i');
    fill.style.width = `${(score * 100).toFixed(0)}%`;
    fill.style.setProperty('--fill', `hsl(${(1 - score) * 120} 80% 52%)`);
    bar.append(fill);
    const text = document.createElement('span');
    text.textContent = `${(score * 100).toFixed(0)}% · ${value?.surface ?? NA}`;
    item.append(name, bar, text);
    return item;
  }));
}

function render(state) {
  lastStateAt = Date.now();
  tickAge();
  for (const button of [...pending]) release(button);

  for (const [key, path] of Object.entries(DISPLAY_PATHS)) {
    const element = $(`v-${key}`);
    if (!element) continue;
    const value = read(state, path);
    if (element.tagName === 'PROGRESS') {
      element.value = typeof value === 'number' ? value : 0;
      $('progress-value').value = typeof value === 'number' ? `${(value * 100).toFixed(0)}%` : NA;
    } else {
      element.textContent = key === 'cargo_type' ? (CARGO_LABELS[value] ?? show(value)) : show(value);
    }
  }

  const status = read(state, 'status');
  const statusNode = $('status');
  statusNode.textContent = show(status);
  statusNode.className = `tone-${statusTone(status)}`;
  // The raw enum, kept out of the visible text so the label can be translated freely.
  statusNode.dataset.status = show(status);
  statusNode.dataset.states = String(++statesRendered);
  const source = read(state, 'source');
  const presentation = SOURCE_PRESENTATION[source];
  $('v-source').textContent = presentation?.label ?? (source ? `${String(source).toUpperCase()} · ที่มาไม่ระบุ` : NA);
  $('progress-label').textContent = presentation?.progress ?? 'ความคืบหน้า';
  $('v-error').textContent = state?.error ?? state?.source_diagnostic ?? 'ไม่มี';

  const distance = read(state, 'obstacle_distance');
  const tone = obstacleTone(distance);
  // "จำลอง" travels with the value, not just with the input control: this distance is an operator
  // input, never a measurement, and a screenshot of it must not suggest a real distance sensor.
  $('v-obstacle_distance').textContent = tone === 'none' ? NA : `จำลอง ${distance} ซม. · ${tone === 'stop' ? 'เขตหยุดปลอดภัย' : tone === 'warn' ? 'เขตชะลอ' : 'ระยะปลอดภัย'}`;

  renderRisk(read(state, 'risk_map'));
  renderTimeline(read(state, 'events'));

  // Reflect engine-side changes without fighting the operator mid-selection.
  if (document.activeElement !== $('cargo')) $('cargo').value = read(state, 'cargo_type') ?? $('cargo').value;

  stage?.apply(state);
  if (state?.error) toast(state.error, true);
}

function tickAge() {
  if (lastStateAt === null) return;
  const seconds = (Date.now() - lastStateAt) / 1000;
  $('age').textContent = seconds < 1 ? 'เมื่อสักครู่' : `${seconds.toFixed(1)} วินาทีที่แล้ว`;
}
setInterval(tickAge, 250);

/* ---------------- transport ---------------- */

function setLink(text, tone) {
  $('link-text').textContent = text;
  $('link-dot').className = `dot dot-${tone}`;
}

client.on('error', (error) => {
  setLink('ผิดพลาด', 'stop');
  $('v-error').textContent = String(error?.message ?? error);
});
client.on('disconnect', () => setLink('ตัดการเชื่อมต่อ', 'stop'));
client.on('reconnect', () => setLink('กำลังเชื่อมต่อใหม่…', 'idle'));
client.on('connect', () => setLink('เชื่อมต่อแล้ว', 'go'));

$('device-id').textContent = deviceId;
$('v-url').textContent = url;
$('v-topic').textContent = topic.state;

try {
  await client.connect();
  setLink('เชื่อมต่อแล้ว', 'go');
  // State is retained, so this renders the last known mission immediately on open.
  await client.subscribe(topic.state, (message) => render(message.payload));
} catch (error) {
  setLink('ออฟไลน์', 'stop');
  $('v-error').textContent = String(error?.message ?? error);
  toast(`เชื่อมต่อ ${url} ไม่สำเร็จ`, true);
}
