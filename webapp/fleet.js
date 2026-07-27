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
const mqttDisabled = params.get('mqtt') === 'off';

const FLEET_STATUS_TOPIC = 'cargoshield/fleet/status';
const HISTORY_REFRESH_MS = 5000;
const PAGE_SIZE = 20;
const DETAIL_ROWS = 200;
const state = {
  events: { page: 1, loading: false },
  missions: { page: 1, loading: false },
};

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
  const segments = [];
  let points = [];
  for (const [index, value] of values.entries()) {
    if (!Number.isFinite(value)) {
      if (points.length) segments.push(points);
      points = [];
      continue;
    }
    const x = (index / (values.length - 1)) * (width - 2) + 1;
    const y = height - 1 - ((value - low) / span) * (height - 2);
    points.push(`${x.toFixed(1)},${y.toFixed(1)}`);
  }
  if (points.length) segments.push(points);
  for (const segment of segments) {
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'polyline');
    path.setAttribute('points', segment.join(' '));
    svg.append(path);
  }
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
let liveRosterSeen = false;

function setKnownRobots(ids) {
  ids = [...new Set(ids.filter((id) => typeof id === 'string' && id))].sort();
  if (ids.join('|') === knownRobots.join('|')) return;
  knownRobots = ids;
  for (const id of ['series-robot', 'copilot-robot']) {
    const select = $(id);
    const previous = select.value;
    select.replaceChildren(...ids.map((robotId) => new Option(robotId, robotId)));
    if (ids.includes(previous)) select.value = previous;
  }
  refreshSeries();
}

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

  liveRosterSeen = true;
  setKnownRobots(robots.map(([robotId]) => robotId));
}

/* ---------------- Maintenance Assistant (read-only, deterministic) ---------------- */

/**
 * Curated questions only. The buttons are built from what `/api/copilot` reports it supports, so
 * this page cannot ask anything the read-only boundary has not allowlisted, and there is no free
 * text box to type one into. Every answer is rendered with its evidence rows.
 */
let copilotQuestions = [];
let activeQuestion = null;

function renderCopilotAnswer(node, payload) {
  const summary = document.createElement('p');
  summary.className = 'answer-summary';
  summary.textContent = text(payload.summary);

  const meta = document.createElement('p');
  meta.className = 'answer-meta';
  meta.textContent =
    `คำถาม: ${text(payload.question)} · วิเคราะห์แบบ deterministic (ไม่มีโมเดลภาษา) · `
    + `หลักฐาน ${(payload.evidence ?? []).length} แถว · สร้างเมื่อ ${clock(payload.generated_ms)}`;

  const rows = payload.evidence ?? [];
  node.replaceChildren(summary, meta);
  if (!rows.length) {
    const empty = document.createElement('p');
    empty.className = 'answer-empty';
    empty.textContent = 'ไม่มีแถวหลักฐานสำหรับคำถามนี้ — ระบบจึงไม่สรุปเกินข้อมูลที่มี';
    node.append(empty);
    return;
  }
  // Columns come from the rows themselves; the API returns fixed SELECT lists, never caller SQL.
  const columns = [...new Set(rows.flatMap((row) => Object.keys(row)))];
  const head = document.createElement('tr');
  for (const column of columns) {
    const heading = document.createElement('th');
    heading.scope = 'col';
    heading.textContent = column;
    head.append(heading);
  }
  const thead = document.createElement('thead');
  thead.append(head);

  const body = document.createElement('tbody');
  for (const row of rows) {
    const line = document.createElement('tr');
    for (const column of columns) {
      const value = row[column];
      cell(line, value !== null && typeof value === 'object' ? JSON.stringify(value) : value, { wrap: true });
    }
    body.append(line);
  }

  const table = document.createElement('table');
  table.className = 'grid';
  table.append(thead, body);

  const scroll = document.createElement('div');
  scroll.className = 'table-scroll';
  scroll.tabIndex = 0;
  scroll.setAttribute('role', 'region');
  scroll.setAttribute('aria-label', 'แถวหลักฐานของคำตอบ');
  scroll.append(table);
  node.append(scroll);
}

async function askCopilot(question) {
  const node = $('copilot-answer');
  activeQuestion = question.id;
  for (const button of $('copilot-questions').children) {
    button.setAttribute('aria-pressed', String(button.dataset.question === question.id));
  }
  const robotId = $('copilot-robot').value;
  if (question.needs_robot && !robotId) {
    node.replaceChildren(Object.assign(document.createElement('p'), {
      className: 'answer-empty',
      textContent: 'คำถามนี้ต้องเลือกหุ่นยนต์ก่อน',
    }));
    return;
  }
  node.replaceChildren(Object.assign(document.createElement('p'), {
    className: 'answer-empty', textContent: 'กำลังอ่านข้อมูล…',
  }));
  const query = question.needs_robot ? `?robot_id=${encodeURIComponent(robotId)}` : '';
  try {
    renderCopilotAnswer(node, await api(`/api/copilot/${question.id}${query}`));
  } catch (error) {
    node.replaceChildren(Object.assign(document.createElement('p'), {
      className: 'answer-empty',
      textContent: `อ่านข้อมูลไม่สำเร็จ: ${error?.message ?? error} — ความปลอดภัยของหุ่นยนต์ไม่ได้ขึ้นกับผู้ช่วยนี้`,
    }));
  }
}

async function loadCopilot() {
  let index;
  try {
    index = await api('/api/copilot');
  } catch (error) {
    $('copilot-answer').replaceChildren(Object.assign(document.createElement('p'), {
      className: 'answer-empty',
      textContent: `ผู้ช่วยบำรุงรักษาไม่พร้อมใช้งาน: ${error?.message ?? error}`,
    }));
    return;
  }
  // The provider line states what the backend actually reports, never an aspiration.
  $('copilot-provider').textContent = index.provider
    ? `Provider: ${index.provider}`
    : 'Hermes provider: Not connected';
  copilotQuestions = index.questions ?? [];
  $('copilot-questions').replaceChildren(...copilotQuestions.map((question) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.question = question.id;
    button.setAttribute('aria-pressed', String(question.id === activeQuestion));
    button.textContent = question.question_th;
    button.addEventListener('click', () => askCopilot(question));
    return button;
  }));
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

function loadingRow(tbody, columns, message = 'กำลังโหลดข้อมูล…') {
  replaceRows(tbody, [], message, columns);
}

function showHistoryUnavailable(message) {
  replaceRows($('event-rows'), [], `History API unavailable: ${message}`, 7);
  replaceRows($('mission-rows'), [], `History API unavailable: ${message}`, 6);
  state.events.metadata = null;
  state.missions.metadata = null;
  renderPager('event', null, 0);
  renderPager('mission', null, 0);
}

function renderPager(prefix, metadata, count) {
  const current = state[prefix === 'event' ? 'events' : 'missions'];
  $(`${prefix}-page`).textContent = `หน้า ${metadata?.page ?? current.page}`;
  $(`${prefix}-range`).textContent = count
    ? `รายการ ${metadata.range_start}–${metadata.range_end}`
    : '0 รายการ';
  $(`${prefix}-prev`).disabled = current.loading || !metadata?.has_previous;
  $(`${prefix}-next`).disabled = current.loading || !metadata?.has_more;
}

async function loadEvents() {
  const current = state.events;
  if (current.loading) return;
  current.loading = true;
  loadingRow($('event-rows'), 7);
  renderPager('event', null, 0);
  const severity = $('event-severity').value;
  const query = new URLSearchParams({ page: String(current.page), limit: String(PAGE_SIZE) });
  if (severity) query.set('severity', severity);
  try {
    const result = await api(`/api/events?${query}`);
    const rows = result.events ?? [];
    replaceRows($('event-rows'), rows.map((event) => {
      const row = document.createElement('tr');
      cell(row, clock(event.observed_ms));
      cell(row, event.robot_id);
      cell(row, event.severity, { tone: SEVERITY_TONE[event.severity] ?? 'idle' });
      cell(row, event.kind);
      cell(row, event.action ?? event.code);
      cell(row, event.health_state, { tone: HEALTH_TONE[event.health_state] ?? 'idle' });
      cell(row, event.reason, { wrap: true });
      return row;
    }), 'ไม่พบเหตุการณ์ตามตัวกรองนี้', 7);
    current.metadata = result;
    renderPager('event', result, rows.length);
  } catch (error) {
    current.metadata = null;
    replaceRows($('event-rows'), [], `History API unavailable: ${error?.message ?? error}`, 7);
    renderPager('event', null, 0);
    throw error;
  } finally {
    current.loading = false;
    renderPager('event', current.metadata, current.metadata?.events?.length ?? 0);
  }
}

async function loadMissions() {
  const current = state.missions;
  if (current.loading) return;
  current.loading = true;
  loadingRow($('mission-rows'), 6);
  renderPager('mission', null, 0);
  try {
    const result = await api(`/api/missions?page=${state.missions.page}&limit=${PAGE_SIZE}`);
    const rows = result.missions ?? [];
    replaceRows($('mission-rows'), rows.map((mission) => {
      const row = document.createElement('tr');
      cell(row, mission.mission_id);
      cell(row, mission.robot_id);
      cell(row, mission.cargo_type);
      cell(row, Array.isArray(mission.route) ? mission.route.join(' → ') : NA, { wrap: true });
      cell(row, num(Number(mission.route_cost), 3));
      cell(row, clock(mission.started_ms));
      return row;
    }), 'ยังไม่มีภารกิจที่บันทึกไว้', 6);
    current.metadata = result;
    renderPager('mission', result, rows.length);
  } catch (error) {
    current.metadata = null;
    replaceRows($('mission-rows'), [], `History API unavailable: ${error?.message ?? error}`, 6);
    renderPager('mission', null, 0);
    throw error;
  } finally {
    current.loading = false;
    renderPager('mission', current.metadata, current.metadata?.missions?.length ?? 0);
  }
}

function csvFilename(response, fallback) {
  const match = response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/);
  return match?.[1] ?? fallback;
}

async function downloadCsv(kind) {
  const eventExport = kind === 'event';
  const button = $(`${kind}-download`);
  const status = $(`${kind}-download-status`);
  const query = new URLSearchParams();
  if (eventExport && $('event-severity').value) query.set('severity', $('event-severity').value);
  const suffix = query.size ? `?${query}` : '';
  const path = eventExport ? `/api/events.csv${suffix}` : '/api/missions.csv';
  button.disabled = true;
  button.setAttribute('aria-busy', 'true');
  status.textContent = 'กำลังเตรียม CSV…';
  try {
    const response = await fetch(`${apiBase}${path}`, { cache: 'no-store' });
    if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
    const rowCount = Number(response.headers.get('X-Row-Count') ?? 0);
    if (!rowCount) {
      status.textContent = 'ไม่มีข้อมูลตามตัวกรอง จึงไม่มีไฟล์ให้ดาวน์โหลด';
      return;
    }
    const objectUrl = URL.createObjectURL(await response.blob());
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = csvFilename(
      response,
      `cargoshield_${eventExport ? 'safety_events' : 'mission_history'}.csv`,
    );
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(objectUrl);
    status.textContent = `ดาวน์โหลด CSV สำเร็จ ${rowCount} รายการ`;
  } catch (error) {
    status.textContent = `ดาวน์โหลดไม่สำเร็จ: ${error?.message ?? error}`;
  } finally {
    button.disabled = false;
    button.removeAttribute('aria-busy');
  }
}

async function refreshHistory() {
  try {
    const health = await api('/api/health');
    setApiStatus(Boolean(health.reachable), health.reachable ? text(health.database) : text(health.reason));
    if (!health.reachable) {
      showHistoryUnavailable(text(health.reason));
      return;
    }
  } catch (error) {
    setApiStatus(false, String(error.message ?? error));
    showHistoryUnavailable(String(error.message ?? error));
    return;
  }

  try {
    const [fleet, zones, findings, quality, exports] = await Promise.all([
      api('/api/fleet'),
      api('/api/zones'),
      api('/api/maintenance?unresolved=0&limit=' + DETAIL_ROWS),
      api('/api/data-quality'), api('/api/exports?limit=1'),
      loadEvents(), loadMissions(),
    ]);

    // With MQTT offline, history still has the registered robot IDs required by its read-only tools.
    // A retained live fleet status takes precedence as soon as it arrives.
    if (!liveRosterSeen) setKnownRobots((fleet.robots ?? []).map((robot) => robot?.robot_id));

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
$('event-severity').addEventListener('change', async () => {
  state.events.page = 1;
  try {
    await loadEvents();
  } catch (error) {
    setApiStatus(false, String(error?.message ?? error));
  }
});
for (const [id, collection, delta] of [
  ['event-prev', 'events', -1], ['event-next', 'events', 1],
  ['mission-prev', 'missions', -1], ['mission-next', 'missions', 1],
]) {
  $(id).addEventListener('click', async () => {
    const current = state[collection];
    current.page = Math.max(1, current.page + delta);
    try {
      await (collection === 'events' ? loadEvents() : loadMissions());
    } catch (error) {
      setApiStatus(false, String(error?.message ?? error));
    }
  });
}
$('event-download').addEventListener('click', () => downloadCsv('event'));
$('mission-download').addEventListener('click', () => downloadCsv('mission'));
// Re-asking on a robot change keeps the answer and the selector from disagreeing on screen.
$('copilot-robot').addEventListener('change', () => {
  const question = copilotQuestions.find((entry) => entry.id === activeQuestion);
  if (question?.needs_robot) askCopilot(question);
});

function setLink(message, tone) {
  $('link-text').textContent = message;
  $('link-dot').className = `dot dot-${tone}`;
}

if (!mqttDisabled) {
  client = new LiveDataClient({
    transport: 'mqtt',
    url,
    clientId: `cargoshield-fleet-${Math.random().toString(36).slice(2, 8)}`,
  });
  client.on('error', () => setLink('ผิดพลาด', 'stop'));
  client.on('disconnect', () => setLink('ตัดการเชื่อมต่อ', 'stop'));
  client.on('reconnect', () => setLink('กำลังเชื่อมต่อใหม่…', 'idle'));
  client.on('connect', () => setLink('เชื่อมต่อแล้ว', 'go'));
} else {
  setLink('ออฟไลน์ · MQTT ปิดอยู่', 'idle');
}

async function connectMqtt() {
  if (!client) return;
  try {
    await client.connect();
    setLink('เชื่อมต่อแล้ว', 'go');
    // Retained, so the summary renders the moment the page opens.
    await client.subscribe(FLEET_STATUS_TOPIC, (message) => renderFleetStatus(message.payload));
  } catch (error) {
    setLink('ออฟไลน์', 'stop');
    toast(`เชื่อมต่อ ${url} ไม่สำเร็จ`, true);
  }
}

// MQTT and history are independent surfaces: an offline robot channel must not leave read-only
// history spinning, and a database outage must not block the live fleet channel.
void connectMqtt();
await Promise.all([refreshHistory(), loadCopilot()]);
setInterval(refreshHistory, HISTORY_REFRESH_MS);
