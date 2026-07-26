/**
 * Fleet Intelligence: cross-robot analysis.
 *
 * Live state comes from MQTT (the retained `cargoshield/fleet/status`). History comes from the
 * narrow read-only HTTP API. The browser never touches PostgreSQL, and this file never derives a
 * status, a health state or a safety action of its own -- it renders what Python published.
 */

import { LiveDataClient, DEFAULT_MQTT_WS_URL } from './live-data.browser.js';

const params = new URLSearchParams(location.search);
const url = params.get('url') ?? DEFAULT_MQTT_WS_URL;
const apiBase = (params.get('api') ?? 'http://127.0.0.1:8099').replace(/\/$/, '');

const FLEET_STATUS_TOPIC = 'cargoshield/fleet/status';
const HISTORY_REFRESH_MS = 5000;
const MAX_ROWS = 50;

const $ = (id) => document.getElementById(id);
const NA = 'N/A';

/* ---------------- small helpers ---------------- */

const text = (value) => (value === undefined || value === null || value === '' ? NA : String(value));
const num = (value, digits = 2) =>
  (typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : NA);

function clock(ms) {
  const value = Number(ms);
  return Number.isFinite(value) && value > 0 ? new Date(value).toLocaleTimeString() : NA;
}

/** Health and severity get a tone class *and* a word, so colour is never the only signal. */
const HEALTH_TONE = { HEALTHY: 'go', DEGRADED: 'hold', UNSAFE: 'stop', OFFLINE: 'idle' };
const SEVERITY_TONE = { info: 'idle', warning: 'hold', critical: 'stop' };

function cell(row, value, { tone = null, wrap = false } = {}) {
  const node = document.createElement('td');
  node.textContent = text(value);
  if (tone) node.className = `tone-${tone}`;
  if (wrap) node.classList.add('wrap');
  row.append(node);
  return node;
}

function replaceRows(tbody, rows, emptyMessage, columns) {
  if (!rows.length) {
    const row = document.createElement('tr');
    const only = document.createElement('td');
    only.colSpan = columns;
    only.textContent = emptyMessage;
    row.append(only);
    tbody.replaceChildren(row);
    return;
  }
  // replaceChildren, always: the table is redrawn from the current answer rather than appended to,
  // so neither the DOM nor the listener set can grow across refreshes.
  tbody.replaceChildren(...rows);
}

function toast(message, bad = false) {
  const host = $('toasts');
  const node = document.createElement('div');
  node.className = bad ? 'toast bad' : 'toast';
  node.textContent = message;
  // Bounded: a repeating error must not stack nodes forever.
  while (host.children.length >= 4) host.firstElementChild.remove();
  host.append(node);
  setTimeout(() => node.remove(), bad ? 6000 : 3000);
}

/** Inline SVG sparkline. No chart library, no CDN, no canvas. */
function sparkline(values, { width = 260, height = 44, tone = 'accent' } = {}) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  svg.setAttribute('class', `spark spark-${tone}`);
  svg.setAttribute('role', 'img');
  const finite = values.filter((value) => Number.isFinite(value));
  if (finite.length < 2) {
    svg.setAttribute('aria-label', 'ข้อมูลไม่พอสำหรับกราฟ');
    return svg;
  }
  const low = Math.min(...finite);
  const high = Math.max(...finite);
  const span = high - low || 1;
  const points = finite.map((value, index) => {
    const x = (index / (finite.length - 1)) * (width - 2) + 1;
    const y = height - 1 - ((value - low) / span) * (height - 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
  path.setAttribute('points', points.join(' '));
  svg.append(path);
  svg.setAttribute('aria-label', `กราฟ ${finite.length} จุด ต่ำสุด ${low.toFixed(3)} สูงสุด ${high.toFixed(3)}`);
  return svg;
}

/* ---------------- read-only history API ---------------- */

let apiHealthy = false;

async function api(path) {
  const response = await fetch(`${apiBase}${path}`, { method: 'GET', cache: 'no-store' });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function setApiStatus(ok, message) {
  apiHealthy = ok;
  $('api-dot').className = `dot dot-${ok ? 'go' : 'stop'}`;
  $('api-text').textContent = message;
  const banner = $('api-error');
  banner.hidden = ok;
  if (!ok) {
    banner.textContent =
      `ประวัติไม่พร้อมใช้งาน: ${message} — ความปลอดภัยของหุ่นยนต์ไม่ได้ขึ้นกับฐานข้อมูลนี้`;
  }
}

/* ---------------- live fleet status over MQTT ---------------- */

let knownRobots = [];

function renderFleetStatus(status) {
  const counts = status?.counts ?? {};
  $('count-total').textContent = text(status?.robot_count);
  $('count-online').textContent = text(counts.online);
  $('count-degraded').textContent = text(counts.degraded);
  $('count-stopped').textContent = text(counts.stopped);
  $('count-offline').textContent = text(counts.offline);

  const historian = status?.historian ?? {};
  $('v-queue').textContent =
    `${text(historian.queue_depth)} / ${text(historian.queue_capacity)} · เขียนแล้ว ${text(historian.written)}`;
  $('v-dropped').textContent =
    `${text(historian.dropped)} · ลองใหม่ ${text(historian.retries)} · แถวที่ล้มเหลว ${text(historian.failed_rows)}`;

  const latency = status?.latency ?? {};
  $('v-latency').textContent = latency.samples
    ? `${num(latency.p50_ms, 3)} / ${num(latency.p95_ms, 3)} / ${num(latency.max_ms, 3)} ms (${latency.samples} ตัวอย่าง)`
    : NA;
  $('v-latency-note').textContent = text(latency.measurement);

  const robots = Object.entries(status?.robots ?? {});
  const rows = robots.map(([robotId, robot]) => {
    const row = document.createElement('tr');
    const health = robot?.health?.state ?? 'OFFLINE';
    cell(row, robotId);
    cell(row, `${text(robot?.status)}${robot?.latched_stop ? ' · ล็อกหยุด' : ''}`,
      { tone: robot?.latched_stop ? 'stop' : null });
    cell(row, health, { tone: HEALTH_TONE[health] ?? 'idle' });
    cell(row, clock(robot?.last_seen_ms));
    cell(row, `${text(robot?.samples)} / ${text(robot?.rejected)}`);
    cell(row, (robot?.health?.quarantined ?? []).join(', ') || '—');
    cell(row, robot?.latch_reason || (robot?.health?.reasons ?? []).join('; ') || '—', { wrap: true });
    return row;
  });
  replaceRows($('robot-rows'), rows, 'ยังไม่ได้รับข้อมูลจากกองหุ่นยนต์', 7);

  const ids = robots.map(([robotId]) => robotId);
  if (ids.join('|') !== knownRobots.join('|')) {
    knownRobots = ids;
    const select = $('series-robot');
    const previous = select.value;
    select.replaceChildren(...ids.map((id) => new Option(id, id)));
    if (ids.includes(previous)) select.value = previous;
    refreshSeries();
  }
}

/* ---------------- history panels ---------------- */

async function refreshSeries() {
  const robotId = $('series-robot').value;
  const host = $('series-charts');
  if (!robotId || !apiHealthy) {
    host.replaceChildren();
    return;
  }
  try {
    const [{ predictions }, { samples }] = await Promise.all([
      api(`/api/predictions?robot_id=${encodeURIComponent(robotId)}&limit=200`),
      api(`/api/telemetry?robot_id=${encodeURIComponent(robotId)}&limit=200`),
    ]);
    // The API returns newest-first; a time series reads oldest-first.
    const ordered = [...predictions].reverse();
    const orderedSamples = [...samples].reverse();
    const channel = (name) => orderedSamples.map((row) => Number(row?.channels?.[name]));

    const series = [
      ['การสั่นสะเทือน (vibration score)', ordered.map((row) => Number(row.vibration_score)), 'stop'],
      ['ความมั่นใจของโมเดล (confidence)', ordered.map((row) => Number(row.confidence)), 'accent'],
      ['อุณหภูมิอากาศ °C (sht40)', channel('sht40.temperatureC'), 'hold'],
      ['ความชื้น %RH (sht40)', channel('sht40.humidityPct'), 'go'],
      ['ความกดอากาศ hPa (dps368)', channel('dps368.pressureHpa'), 'idle'],
    ];
    host.replaceChildren(...series.map(([label, values, tone]) => {
      const figure = document.createElement('figure');
      figure.className = 'series-item';
      const caption = document.createElement('figcaption');
      const finite = values.filter(Number.isFinite);
      caption.textContent = finite.length
        ? `${label} — ล่าสุด ${finite.at(-1).toFixed(3)} (${finite.length} จุด)`
        : `${label} — ไม่มีข้อมูล`;
      figure.append(caption, sparkline(values, { tone }));
      return figure;
    }));
  } catch (error) {
    host.replaceChildren();
    setApiStatus(false, String(error.message ?? error));
  }
}

const RISK_WORD = (score) => (score >= 0.8 ? 'สูง (high)' : score >= 0.5 ? 'ปานกลาง (medium)' : 'ต่ำ (low)');

async function refreshHistory() {
  try {
    const health = await api('/api/health');
    setApiStatus(Boolean(health.reachable), health.reachable ? text(health.database) : text(health.reason));
    if (!health.reachable) return;
  } catch (error) {
    setApiStatus(false, String(error.message ?? error));
    return;
  }

  try {
    const severity = $('event-severity').value;
    const [zones, missions, events, findings, quality, exports] = await Promise.all([
      api('/api/zones'), api(`/api/missions?limit=${MAX_ROWS}`),
      api(`/api/events?limit=${MAX_ROWS}${severity ? `&severity=${severity}` : ''}`),
      api('/api/maintenance?unresolved=0&limit=' + MAX_ROWS),
      api('/api/data-quality'), api('/api/exports?limit=1'),
    ]);

    replaceRows($('zone-rows'), (zones.zones ?? []).map((zone) => {
      const row = document.createElement('tr');
      const mean = Number(zone.mean_vibration) || 0;
      cell(row, zone.zone);
      cell(row, zone.samples);
      cell(row, num(Number(zone.mean_vibration), 3));
      cell(row, num(Number(zone.peak_vibration), 3));
      cell(row, zone.high_risk_samples);
      cell(row, RISK_WORD(mean), { tone: mean >= 0.8 ? 'stop' : mean >= 0.5 ? 'hold' : 'go' });
      return row;
    }), 'ยังไม่มีข้อมูลโซน', 6);

    replaceRows($('mission-rows'), (missions.missions ?? []).map((mission) => {
      const row = document.createElement('tr');
      cell(row, mission.mission_id);
      cell(row, mission.robot_id);
      cell(row, mission.cargo_type);
      cell(row, Array.isArray(mission.route) ? mission.route.join(' → ') : NA, { wrap: true });
      cell(row, num(Number(mission.route_cost), 3));
      cell(row, clock(mission.started_ms));
      return row;
    }), 'ยังไม่มีภารกิจที่บันทึกไว้', 6);

    replaceRows($('event-rows'), (events.events ?? []).map((event) => {
      const row = document.createElement('tr');
      cell(row, clock(event.observed_ms));
      cell(row, event.robot_id);
      cell(row, event.severity, { tone: SEVERITY_TONE[event.severity] ?? 'idle' });
      cell(row, event.kind);
      cell(row, event.action ?? event.code);
      cell(row, event.health_state, { tone: HEALTH_TONE[event.health_state] ?? 'idle' });
      cell(row, event.reason, { wrap: true });
      return row;
    }), 'ยังไม่มีเหตุการณ์', 7);

    replaceRows($('maintenance-rows'), (findings.findings ?? []).map((finding) => {
      const row = document.createElement('tr');
      const open = finding.acknowledged_ms === null || finding.acknowledged_ms === undefined;
      cell(row, finding.robot_id);
      cell(row, finding.severity, { tone: SEVERITY_TONE[finding.severity] ?? 'idle' });
      cell(row, finding.reason, { wrap: true });
      cell(row, clock(finding.opened_ms));
      cell(row, open ? 'ค้างอยู่ (unresolved)' : `รับทราบแล้ว ${clock(finding.acknowledged_ms)}`,
        { tone: open ? 'hold' : 'go' });
      const action = document.createElement('td');
      if (open) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'ghost';
        button.textContent = 'รับทราบ (acknowledge)';
        button.addEventListener('click', () => acknowledge(finding.robot_id, button));
        action.append(button);
      } else {
        action.textContent = '—';
      }
      row.append(action);
      return row;
    }), 'ไม่มีงานค้าง', 6);

    const provenance = quality.provenance ?? [];
    const total = provenance.reduce((sum, entry) => sum + Number(entry.samples || 0), 0) || 1;
    $('quality-list').replaceChildren(...(provenance.length ? provenance : [{ provenance: '—', samples: 0 }]).map((entry) => {
      const item = document.createElement('li');
      const share = Number(entry.samples || 0) / total;
      const name = document.createElement('b');
      name.textContent = entry.provenance;
      const bar = document.createElement('span');
      bar.className = 'bar';
      const fill = document.createElement('i');
      fill.style.width = `${(share * 100).toFixed(0)}%`;
      fill.style.setProperty('--fill', 'var(--accent)');
      bar.append(fill);
      const label = document.createElement('span');
      label.textContent = `${entry.samples} ตัวอย่าง · ${(share * 100).toFixed(0)}%`;
      item.append(name, bar, label);
      return item;
    }));

    const manifest = (exports.manifests ?? [])[0];
    $('export-manifest').textContent = manifest ? JSON.stringify(manifest, null, 2) : 'ยังไม่มีการส่งออก';

    // The robot list arrives over MQTT, which usually wins the race against this first health
    // check, so the series drawn at that moment were skipped as "API not ready". Redraw them here,
    // once the API is known to be reachable.
    await refreshSeries();
  } catch (error) {
    setApiStatus(false, String(error.message ?? error));
  }
}

/* ---------------- operator command (write path, MQTT only) ---------------- */

let client = null;

async function acknowledge(robotId, button) {
  if (!client) {
    toast('ยังไม่ได้เชื่อมต่อ MQTT จึงส่งคำสั่งไม่ได้', true);
    return;
  }
  button.disabled = true;
  try {
    // Acknowledgement travels on the command topic, never through the read-only history API.
    await client.publish(`cargoshield/${robotId}/command`, { action: 'acknowledge', note: 'acknowledged from Fleet Intelligence' });
    toast(`ส่งคำสั่งรับทราบให้ ${robotId} แล้ว`);
  } catch (error) {
    toast(`ส่งคำสั่งไม่สำเร็จ: ${error?.message ?? error}`, true);
  } finally {
    button.disabled = false;
  }
}

/* ---------------- export command builder ---------------- */

function renderExportCommand() {
  const robots = $('export-robots').value.trim();
  const provenance = $('export-provenance').value;
  const format = $('export-format').value;
  const parts = ['.\\.venv\\Scripts\\python.exe', '-m', 'cargo.export', '--format', format];
  if (robots) parts.push('--robots', robots);
  if (provenance) parts.push('--provenance', provenance);
  $('export-command').textContent = parts.join(' ');
}

/* ---------------- wiring ---------------- */

for (const id of ['export-robots', 'export-provenance', 'export-format']) {
  $(id).addEventListener('change', renderExportCommand);
  $(id).addEventListener('input', renderExportCommand);
}
renderExportCommand();

$('series-robot').addEventListener('change', refreshSeries);
$('event-severity').addEventListener('change', refreshHistory);

function setLink(message, tone) {
  $('link-text').textContent = message;
  $('link-dot').className = `dot dot-${tone}`;
}

client = new LiveDataClient({
  transport: 'mqtt',
  url,
  clientId: `cargoshield-fleet-${Math.random().toString(36).slice(2, 8)}`,
});
client.on('error', () => setLink('ผิดพลาด', 'stop'));
client.on('disconnect', () => setLink('ตัดการเชื่อมต่อ', 'stop'));
client.on('reconnect', () => setLink('กำลังเชื่อมต่อใหม่…', 'idle'));
client.on('connect', () => setLink('เชื่อมต่อแล้ว', 'go'));

try {
  await client.connect();
  setLink('เชื่อมต่อแล้ว', 'go');
  // Retained, so the summary renders the moment the page opens.
  await client.subscribe(FLEET_STATUS_TOPIC, (message) => renderFleetStatus(message.payload));
} catch (error) {
  setLink('ออฟไลน์', 'stop');
  toast(`เชื่อมต่อ ${url} ไม่สำเร็จ`, true);
}

await refreshHistory();
setInterval(refreshHistory, HISTORY_REFRESH_MS);
