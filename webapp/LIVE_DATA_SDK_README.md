# @bitstream/live-data

Unified real-time data client for web applications consuming live data (sensor telemetry and more) from Bitstream Studio. One API, two transports:

| Transport | Protocol | Default endpoint |
|---|---|---|
| `websocket` | T3D WebSocket broker | `ws://127.0.0.1:9998` |
| `mqtt` | MQTT broker (over WebSocket in browsers) | `ws://127.0.0.1:8883` (WS) / `mqtt://127.0.0.1:1883` (TCP, Node only) |

Works in browsers, web workers, and Node ≥ 20 (Node ≥ 21 needed for the `websocket` transport's global `WebSocket`).

## Install

```bash
# from a tarball (npm pack in this folder)
npm install ./bitstream-live-data-0.1.0.tgz

# or as a file dependency
npm install file:../Bitstream-Studio/packages/live-data
```

## Quick start

```ts
import { LiveDataClient, DEFAULT_T3D_WS_URL } from '@bitstream/live-data';

const client = new LiveDataClient({
  transport: 'websocket',          // or 'mqtt'
  url: DEFAULT_T3D_WS_URL,         // ws://127.0.0.1:9998
  identity: { role: 'webapp', name: 'demo-dashboard' },
});

await client.subscribe('sensors/+/temp', (msg) => {
  console.log(msg.topic, msg.payload); // parsed JSON
});

await client.publish('app/commands/led', { on: true });
```

Switching to MQTT is one line:

```ts
const client = new LiveDataClient({
  transport: 'mqtt',
  url: 'ws://127.0.0.1:8883',      // Bitstream Studio MQTT-over-WebSocket port
});
```

## API

### `new LiveDataClient(options)`

| Option | Type | Notes |
|---|---|---|
| `transport` | `'websocket' \| 'mqtt'` | required |
| `url` | `string` | required |
| `autoConnect` | `boolean` | default `true` |
| `reconnectPeriod` | `number` | base backoff ms, default `1000` |
| `maxReconnectAttempts` | `number` | `-1` = unlimited, default `10` |
| `connectTimeout` | `number` | default `15000` |
| `identity` | `{ role?, name?, instance?, meta? }` | T3D only: labels session in broker logs |
| `clientId`, `username`, `password` | `string` | MQTT only |

### Methods

- `connect(): Promise<void>` / `disconnect(): Promise<void>`
- `subscribe(topic, handler?, { qos?, binary? }): Promise<void>` — MQTT-style `+`/`#` wildcards on both transports. `binary: true` selects the T3D binary channel (ignored for MQTT).
- `unsubscribe(topic, handler?): Promise<void>`
- `publish(topic, payload, { qos?, retain? }): Promise<void>` — objects are JSON-encoded; strings sent as-is. `retain` is MQTT only.
- `publishBinary(topic, bytes, { qos? }): Promise<void>`
- `on(event, handler): () => void` — events: `connect`, `disconnect`, `reconnect`, `state`, `error`, `message` (all messages). Returns an unsubscribe function.
- `state` / `connected` getters.

### Messages

```ts
interface LiveMessage {
  topic: string;
  payload: unknown;      // parsed JSON (or string); undefined when binary
  raw?: Uint8Array;      // always set for MQTT; set for T3D binary channel
  binary: boolean;
  qos: 0 | 1 | 2;
  transport: 'websocket' | 'mqtt';
}
```

MQTT payloads are auto-detected: valid JSON → parsed object, other UTF-8 → string, otherwise `binary: true` with bytes in `raw`.

## React example

```tsx
import { useEffect, useState } from 'react';
import { LiveDataClient } from '@bitstream/live-data';

function useLiveTopic(client: LiveDataClient, topic: string) {
  const [value, setValue] = useState<unknown>(null);
  useEffect(() => {
    const handler = (msg: { payload: unknown }) => setValue(msg.payload);
    void client.subscribe(topic, handler);
    return () => void client.unsubscribe(topic, handler);
  }, [client, topic]);
  return value;
}
```

## Sensor telemetry (typed, the 4 on-board sensors)

Bitstream Studio's sensor data (BMI270 IMU + fusion, BMM350 magnetometer, SHT40 temp/humidity, DPS368 pressure) is served by the telemetry provider on `ws://127.0.0.1:9997`. `TelemetryClient` speaks that protocol with full typings:

```ts
import { TelemetryClient, SENSOR_CATALOG } from '@bitstream/live-data';

const t = new TelemetryClient();            // ws://127.0.0.1:9997
await t.connect();

t.on('catalog', (c) => console.log(c.sensors.map(s => s.label)));   // pushed on connect
t.on('connection', (c) => console.log(c.state, c.route));           // uart | simulator

t.onSensor('sht40', (s) => {
  console.log(s.fields.temperatureC, '°C,', s.fields.humidityPct, '%RH');
});
t.onSensor('bmi270', (s) => {
  console.log('accel', s.fields.accelX, s.fields.accelY, s.fields.accelZ);
});

// Configure sensors (publish interval, mode, mask...)
await t.command('sensor.cfg.set', { sensor: 'sht40', publishIntervalMs: 500 });
```

Samples arrive human-scaled (`fields` + `units`, wire scaling already applied). `SENSOR_CATALOG` ships in the package: field labels/units/ranges per sensor for building dashboards. Field presence depends on the configured publish mask, hence all fields are optional. Events: `catalog`, `config`, `sample`, `connection`, `hello`, `stale`, `response`.

Raw topic access (e.g. `bitstream2/evt/sensor` on the :9998 broker) remains available via `LiveDataClient`.

## Advanced

The underlying clients are exported for direct use: `T3DWebSocketClient` (full T3D protocol: QoS 0–2 acks, binary channel, hello identity) and `MqttAdapter` (mqtt.js wrapper).

## Development

```bash
npm install
npm run build       # tsup: ESM + CJS + .d.ts in dist/
npm test            # e2e against in-process T3D + Aedes brokers (build first)
npm pack            # tarball for consuming apps
```

Protocol reference: `extension/src/websocket/ARCHITECTURE.md` (T3D) and `extension/src/mqtt/aedes/` (broker) in Bitstream-Studio.
