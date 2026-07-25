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

for (const [select, options] of [[$('cargo'), CARGO_TYPES], [$('pickup'), ZONES], [$('destination'), ZONES]]) {
  select.append(...options.map((value) => new Option(value, value)));
}
$('pickup').value = 'A1';
$('destination').value = 'C2';

const client = new LiveDataClient({ transport: 'mqtt', url, clientId: `cargoshield-console-${deviceId}` });

const pending = new Set();
const sentAt = new Map();
// A demo is a live system: one accidental double-click must not queue two missions. Keyed on the
// payload, so changing pickup and destination in quick succession still sends both commands.
const MIN_REPEAT_MS = 400;

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
  try {
    await client.publish(topic.command, payload);
  } catch (error) {
    release(button);
    toast(`publish failed: ${error?.message ?? error}`, true);
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
$('obstacle').addEventListener('input', (event) => { $('obstacle-value').value = event.target.value; });
$('obstacle-send').addEventListener('click', (event) => send('set_obstacle', COMMANDS.set_obstacle($('obstacle').value), event.currentTarget));

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
  for (const button of [...pending]) release(button);

  for (const [key, path] of Object.entries(DISPLAY_PATHS)) {
    const element = $(`v-${key}`);
    if (!element) continue;
    const value = read(state, path);
    if (element.tagName === 'PROGRESS') {
      element.value = typeof value === 'number' ? value : 0;
      $('progress-value').value = typeof value === 'number' ? `${(value * 100).toFixed(0)}%` : NA;
    } else {
      element.textContent = show(value);
    }
  }

  const status = read(state, 'status');
  $('status').textContent = show(status);
  $('status').className = `tone-${statusTone(status)}`;
  $('v-source').textContent = show(read(state, 'source'));
  $('v-error').textContent = state?.error ?? state?.source_diagnostic ?? 'none';

  const distance = read(state, 'obstacle_distance');
  const tone = obstacleTone(distance);
  $('v-obstacle_distance').textContent = tone === 'none' ? NA : `${distance} cm · ${tone === 'stop' ? 'stop region' : tone === 'warn' ? 'slow region' : 'clear'}`;

  renderRisk(read(state, 'risk_map'));
  renderTimeline(read(state, 'events'));

  // Reflect engine-side changes without fighting the operator mid-selection.
  if (document.activeElement !== $('cargo')) $('cargo').value = read(state, 'cargo_type') ?? $('cargo').value;

  stage?.apply(state);
  if (state?.error) toast(state.error, true);
}

setInterval(() => {
  if (lastStateAt === null) return;
  const seconds = (Date.now() - lastStateAt) / 1000;
  $('age').textContent = seconds < 1 ? 'just now' : `${seconds.toFixed(1)} s ago`;
}, 250);

/* ---------------- transport ---------------- */

function setLink(text, tone) {
  $('link-text').textContent = text;
  $('link-dot').className = `dot dot-${tone}`;
}

client.on('error', (error) => {
  setLink('error', 'stop');
  $('v-error').textContent = String(error?.message ?? error);
});
client.on('disconnect', () => setLink('disconnected', 'stop'));
client.on('reconnect', () => setLink('reconnecting…', 'idle'));
client.on('connect', () => setLink('connected', 'go'));

$('device-id').textContent = deviceId;
$('v-url').textContent = url;
$('v-topic').textContent = topic.state;

try {
  await client.connect();
  setLink('connected', 'go');
  // State is retained, so this renders the last known mission immediately on open.
  await client.subscribe(topic.state, (message) => render(message.payload));
} catch (error) {
  setLink('offline', 'stop');
  $('v-error').textContent = String(error?.message ?? error);
  toast(`cannot reach ${url}`, true);
}
