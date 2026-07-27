# CargoShield AI — สรุปสถานะโปรเจกต์

## โปรเจกต์นี้กำลังทำอะไร

**CargoShield AI** คือระบบ AI สำหรับหุ่นยนต์บริการที่ขนส่งสินค้าในคลังสินค้า ห้าง โรงพยาบาล หรือโรงงาน
ชื่อ `CargoShield Edge` ในเอกสารหรือ artifact รุ่นเก่าหมายถึง prototype เดียวกัน

แนวคิดหลักคือ:

> หุ่นยนต์ไม่ได้สนใจเพียงว่าจะไปถึงปลายทางหรือไม่ แต่ต้องสนใจด้วยว่าสินค้าจะไปถึงโดยไม่เสียหายหรือไม่

ระบบใช้ข้อมูลการเคลื่อนไหวและแรงสั่นสะเทือนจาก IMU เพื่อ:

- จำแนกลักษณะพื้นผิวหรือรูปแบบการสั่น
- ประเมินความเสี่ยงต่อสินค้า
- ปรับความเร็วตามประเภทสินค้า
- เลือกเส้นทางที่เหมาะสม
- จดจำพื้นที่เสี่ยง
- ชะลอ หยุดรอ หรือหยุดฉุกเฉิน
- แสดงผลผ่าน Mission Protection Console และ Fleet Guardian ใน `webapp/` *(เสร็จแล้ว)*
  พร้อมรองรับ Sensor Studio state viewer แบบเสริม

---

## สถาปัตยกรรมระบบ

```text
DATASET / SIMULATED telemetry
            ↓
Python CargoShield services
- Surface AI + confidence gate
- Cargo-aware Safety Core
- Route Risk Memory
- Multi-robot health / isolation
       ├──────── MQTT state/events ────────┐
       │                                   │
       │                                   ├─► webapp/index.html
       │                                   │   Mission Protection + Three.js
       │                                   └─► Sensor Studio state viewer (เสริม)
       │
       └─ bounded historian queue ─► PostgreSQL
                                      ↓
                               History API :8099
                                      ↓
                         Fleet Guardian + Maintenance Assistant
```

Python เป็นสมองหลัก ส่วนหน้าเว็บ, Sensor Studio state viewer, PostgreSQL และ Maintenance Assistant
อยู่นอก synchronous safety path และไม่มีสิทธิ์เปลี่ยนคำตัดสินของ Safety Core

**ฉาก 3D เป็น visualization เท่านั้น** ทุกค่าที่วาดบนจอ ทั้งสถานะ การตัดสินใจ speed ratio คลาสพื้นผิว
zone risk และเส้นทาง อ่านมาจาก state ที่ Python publish ทั้งหมด ไม่มีโค้ดใน `webapp/` ที่ทำ inference
ใช้ policy หรือเดินภารกิจเอง หุ่นยนต์บนจอจะเคลื่อนที่ก็ต่อเมื่อ engine รายงาน `MOVING` หรือ `SLOWING`
ความเร็วของ animation คือ `last.decision.speed_ratio` ของ engine เอง และ `PAUSED` / `HOLDING` /
`SAFE_STOPPED` / `COMPLETED` จะหยุดภาพนิ่งตรงจุดที่ state ล่าสุดบอกไว้ ค่าไหนที่ engine ไม่ได้ส่งมา
หน้าจอแสดง `N/A` และวัตถุ 3D ที่เกี่ยวข้องจะไม่ถูกวาด

### ข้อจำกัดของ Sensor Studio 0.1.9 ที่ติดตั้ง

Build นี้รัน release profile `minimal-sensor` ซึ่ง **ปิด Dashboard pane และ palette หมวด `dashboard` ทั้งหมด** และปิดหมวด `scene` กับ `generator` ด้วย ตรวจแล้วว่า tier profile ทั้งสามที่มากับตัวติดตั้ง (`tier-basic`, `tier-pro`, `tier-pro-plus`) ปิดเหมือนกันหมด ไม่มี tier ไหนเปิดให้

ผลคือใน Library **ไม่มี** `dashboard-button`, `dashboard-select`, `dashboard-slider`, `dashboard-knob` ดังนั้น canvas ของ Sensor Studio สร้างเป็นแผงควบคุมไม่ได้ ทำได้แค่เป็นจอแสดงผลที่ subscribe state

คำสั่งจากผู้ควบคุมจึงย้ายไปที่ `webapp/index.html` ซึ่งเป็นหน้าเว็บโลคอลที่ใช้ Live-Data SDK ที่มากับส่วนขยายเอง (`live-data.browser.js`) คุยกับ broker ผ่าน MQTT-over-WebSocket พอร์ต `8883`

รายละเอียดหลักฐานอยู่ใน `docs/BITSTREAM_VISUAL_FLOW_CAPABILITIES.md`

### วิธีเปิด 3D Operator Console

```powershell
# 1. broker ต้องเปิดอยู่ (Bitstream Studio: Start MQTT Broker) แล้วรัน engine
.\.venv\Scripts\python.exe -m cargo.mqtt_service --host 127.0.0.1 --port 1883

# 2. เสิร์ฟหน้าเว็บ — ใช้ Ctrl+Shift+P -> Serve Web App Folder over HTTP เลือกโฟลเดอร์ webapp
#    หรือใช้ static server อะไรก็ได้ เพราะเป็น ES modules ล้วน ไม่มี build step
.\.venv\Scripts\python.exe -m http.server 8080 --bind 127.0.0.1 --directory webapp

# 3. เปิด http://127.0.0.1:8080/   (state ถูก retain จึงเห็นภารกิจล่าสุดทันทีที่เปิด)

# 4. ตรวจหน้าเว็บอัตโนมัติกับ broker จริง + เก็บ screenshot
.\.venv\Scripts\python.exe scripts\webapp_ui_check.py --url http://127.0.0.1:8080/
```

Three.js 0.180.0 (MIT) อยู่ใน `webapp/vendor/three/` ทั้งหมด ไม่มีการเรียก CDN ใด ๆ วันสาธิตจึงไม่ต้องมี
อินเทอร์เน็ต และไม่มีโมเดล/เท็กซ์เจอร์/ฟอนต์ภายนอก ทุกอย่างในฉากสร้างจาก primitive ของ Three.js และ
เท็กซ์เจอร์ที่วาดด้วย canvas ตอนรันไทม์

### MQTT Topics

คำสั่งจาก `webapp/index.html` ไป Python
(หรือจาก Sensor Studio ในอนาคตหาก build เปิด input widgets):

```text
cargoshield/cargo-robot-01/command
```

สถานะจาก Python กลับ Sensor Studio:

```text
cargoshield/cargo-robot-01/state
```

ข้อมูล DevKit สำหรับการวิเคราะห์เชิงวินิจฉัย:

```text
device/+/devkit-twin/telemetry
```

State ปกติถูก publish แบบ `retain=True` ดังนั้น Flow ที่ subscribe ทีหลังจะได้ State ล่าสุดทันทีโดยไม่ต้องรอให้มีคนกดปุ่ม ส่วน `error` และ `source_diagnostic` ใช้ `retain=False` เพื่อไม่ให้ข้อความชั่วคราวค้างเป็น State ประจำ Topic

---

## ตัวอย่างการทำงาน

### สินค้าทั่วไป

ระบบให้ความสำคัญกับ:

- เส้นทางสั้น
- เวลาเดินทาง
- ประสิทธิภาพ

### สินค้าเปราะบาง

ระบบให้ความสำคัญกับ:

- เส้นทางที่สั่นน้อย
- ความปลอดภัยของสินค้า
- การลดความเร็วในพื้นที่เสี่ยง

### การตอบสนองต่อความเสี่ยง

```text
ความเสี่ยงต่ำ
→ เคลื่อนที่ด้วยความเร็วที่เหมาะสม
```

```text
AI มีความมั่นใจต่ำ
→ HOLDING
→ HOLD_UNCERTAIN
→ speed_ratio = 0.0
```

```text
Obstacle distance = 50
→ SLOW_DOWN
→ speed_ratio = 0.5
```

```text
Obstacle distance = 20
→ SAFE_STOP
→ speed_ratio = 0.0
```

### Obstacle contract

`set_obstacle` และ `clear_obstacle` จะคำนวณคำสั่งใหม่ทันทีจาก inference ล่าสุด **เฉพาะเมื่อ**ภารกิจอยู่ในสถานะทำงาน (`READY`, `MOVING`, `SLOWING`, `HOLDING`, `PAUSED`, `SAFE_STOPPED`) และมีผลโมเดลจริงอยู่แล้ว

- `IDLE` และ `COMPLETED` จะบันทึกเฉพาะค่า `obstacle_distance` ไม่สร้างการเคลื่อนที่ใหม่จากข้อมูลของรอบที่จบไปแล้ว
- ระหว่าง `PAUSED` สิ่งกีดขวางระดับเตือนจะไม่ปลดสถานะหยุดพัก แต่ `SAFE_STOP` มีสิทธิ์เหนือกว่าเสมอ
- `SAFE_STOP` ปิดรอบ replay นั้นถาวร **ณ วินาทีที่ latch เกิด** ไม่ว่าจะเกิดจากคำสั่งของผู้ควบคุมหรือจากหน้าต่างข้อมูลภายในรอบเอง `manual_resume` ปลดล็อกได้แต่ไม่ทำให้ replay เดิมเดินต่อ ผู้ควบคุมต้องกด **Start** ใหม่เท่านั้น
- ถ้ากด Start ใหม่ทั้งที่สิ่งกีดขวางยังอยู่ในระยะหยุด ระบบจะ `SAFE_STOP` ซ้ำ ไม่วิ่งฝ่าออกไป
- สิ่งกีดขวางมีสิทธิ์ **จำกัด** การเคลื่อนที่เท่านั้น เมื่อไม่มีรอบใดกำลังเดินหน้าต่างข้อมูลอยู่ การเคลียร์สิ่งกีดขวางจะคืนสถานะเป็น `READY` ไม่ใช่ `MOVING` แดชบอร์ดจึงไม่แสดงว่าหุ่นยนต์กำลังวิ่งทั้งที่ไม่มีอะไรเดิน

เมื่อเข้า `SAFE_STOP` การล้างสิ่งกีดขวางอย่างเดียวจะไม่ทำให้หุ่นยนต์เคลื่อนที่ ต้องใช้:

```json
{"action":"manual_resume"}
```

`manual_resume` เป็นปุ่มเดียวที่ทำสองหน้าที่ คือทั้ง **Resume** จาก `pause` และ **Clear Safe Stop** ที่ล็อกไว้ ไม่มีคำสั่ง `resume` แยกต่างหาก ดังนั้น Dashboard ควรตั้งชื่อปุ่มให้ครอบคลุมทั้งสองกรณี เช่น `Resume / Clear Safe Stop`

---

## ความสามารถหลัก

### 1. Surface Classification

ระบบใช้ข้อมูล IMU เพื่อจำแนกลักษณะพื้นผิวหรือแรงสั่นสะเทือน

ตัวอย่างคลาสจาก Dataset Replay:

- `carpet`
- `concrete`
- `hard_tiles`
- `tiled`
- `soft_pvc`

### Curated dataset demonstration sequence

รอบสาธิตใช้ชุด index คงที่ 10 หน้าต่างจาก validation split ที่ไม่อยู่ใน train split (`cargo.mqtt_service.DEMO_SEQUENCE`) เว้นระยะหน้าต่างละ `REPLAY_INTERVAL_S = 1.0` วินาที รวมประมาณ 10 วินาทีต่อรอบ ปรับจังหวะได้ด้วย `--interval` โดยไม่ต้องแก้ว่าใช้ข้อมูลหน้าต่างไหน ชุดนี้เป็น Dataset Replay ไม่ใช่การวัดเซนเซอร์สด และไม่ใช้แทนผลประเมินจาก test split

ชุดนี้ถูกเลือกให้ครอบคลุมทั้ง vibration risk `low`, `medium`, `high` และทั้งกรณีที่โมเดลมั่นใจและไม่มั่นใจ **ค่าที่แสดงทุกตัวเป็นผลจริงของโมเดลบนหน้าต่างจริง ไม่มีการปลอมค่า confidence หรือผลทำนาย และไม่มีการลด `minimum_confidence`**

นี่คือ *ลำดับสาธิต* ไม่ใช่ผลการประเมิน ตัวเลขประสิทธิภาพแบบ held-out อ่านได้จาก `reports/metrics.json` ที่เดียวเท่านั้น

ผลลัพธ์ประกอบด้วย:

- Surface label
- Confidence
- Vibration risk
- Current zone
- Recommended action
- Speed ratio

### 2. Cargo-Aware Policy

ระบบมีนโยบายสำหรับสินค้าอย่างน้อยสองแบบ:

- `standard` — เน้นเส้นทางสั้นและประสิทธิภาพ
- `fragile` — เน้นความมั่นคงและลดแรงสั่นสะเทือน

### 3. Zone Risk Map

ระบบจดจำความเสี่ยงของแต่ละโซน เช่น:

```json
{
  "A1": {
    "score": 0.596,
    "observations": 3,
    "surface": "hard_tiles"
  }
}
```

ข้อมูลนี้สามารถนำไปเพิ่มต้นทุนของเส้นทางที่มีความเสี่ยงในภารกิจครั้งถัดไป

**เส้นทางของภารกิจที่กำลังดำเนินอยู่จะไม่เปลี่ยนกลางคัน** ระหว่าง replay ระบบยังบันทึก `risk_map` ทุกหน้าต่างตามปกติ แต่ `route` ที่ publish คงที่ตลอดรอบ ทุกค่า `last.zone` จึงเป็นโหนดใน `route` ที่แดชบอร์ดกำลังแสดงเสมอ การวางเส้นทางใหม่จากความเสี่ยงที่เรียนรู้ไว้จะเกิดตอนกด **Start** รอบถัดไป

ความต่างของเส้นทางระหว่าง `standard` กับ `fragile` จึงปรากฏตั้งแต่รอบที่สองเป็นต้นไป รอบแรกที่ `risk_map` ยังว่าง ทั้งสองแบบเลือกเส้นทางสั้นเหมือนกัน

### 4. Collision Safety

ระบบมี Logic สำหรับ:

- ชะลอเมื่อสิ่งกีดขวางอยู่ใกล้
- หยุดแบบ `SAFE_STOP` เมื่อใกล้มาก
- ล็อกการหยุดไว้จนกว่าจะได้รับ `manual_resume`

### 5. Low-Confidence Safety Hold

เมื่อโมเดลไม่มั่นใจ ระบบจะใช้:

```text
status = HOLDING
action = HOLD_UNCERTAIN
speed_ratio = 0.0
```

`HOLDING` เป็นสถานะเตือน ไม่ใช่โปรแกรม Error และควรแสดงเป็นสีเหลืองหรือสีอำพัน

---

## สิ่งที่ทำเสร็จแล้ว

- Dataset Replay ใช้งานได้โดยไม่ต้องมีบอร์ด
- โมเดล AI ทำ inference ได้
- Cargo policy สำหรับ `standard` และ `fragile` ทำงาน
- Route planning ทำงาน
- Zone Risk Map ทำงาน
- Obstacle Logic ทำงาน
- Safe Stop Latch ทำงาน
- Manual Resume ทำงาน
- แก้ `HOLD_UNCERTAIN` จาก `ERROR` เป็น `HOLDING` แล้ว
- MQTT command/state round trip ทำงาน
- เพิ่ม MQTT smoke test แล้ว
- เพิ่ม `last.risk` ใน State Payload แล้ว
- BLE เดิมไม่ได้ถูกแก้
- Firmware, VSIX, HEX และ Flasher ไม่ได้ถูกแก้
- State ปกติ retain แล้ว Flow ที่ subscribe ทีหลังจึงเห็นสถานะทันที
- Obstacle controls ตอบสนองทันทีต่อ input จำลองตาม contract ด้านบนแล้ว
- Replay เป็นชุดสาธิต 10 หน้าต่าง ~10 วินาที แสดงครบทั้ง MOVE, HOLD_UNCERTAIN และความต่างของ cargo policy
- ตรวจ end-to-end ผ่าน broker จริงด้วย `scripts/demo_e2e_check.py` เก็บหลักฐานไว้ที่ `reports/demo_e2e_evidence.json` (14/14)
- **3D Operator Console ใน `webapp/` เสร็จแล้ว** ฉากคลังสินค้า Three.js แบบ procedural,
  โซน `A1..C2` จาก `DEMO_GRAPH`, เส้นทางจาก `route.nodes`, heat overlay จาก `risk_map`,
  AGV พร้อมสินค้า standard/fragile, obstacle marker, กล้อง Overview / Follow / Robot POV,
  orbit/pan/zoom, no-WebGL fallback และ reduced-motion
- **Fleet Guardian เสร็จแล้ว** แสดงสถานะหลายหุ่นยนต์, ประวัติจาก PostgreSQL, ตาราง
  Safety Events และ Mission History แบบแยกหน้าไม่เกิน 20 แถว, CSV ตามตัวกรอง และ
  Maintenance Assistant แบบ deterministic read-only
- เปิดหน้าเว็บจริงในเบราว์เซอร์และทดสอบครบทั้งลำดับสาธิตกับ broker จริงแล้ว ไม่มี console error เก็บหลักฐานที่ `reports/webapp_ui_evidence.json` และภาพที่ `reports/screenshots/`
- Three.js 0.180.0 (MIT) เก็บไว้ในเครื่องที่ `webapp/vendor/three/` ไม่ใช้ CDN ไม่มี asset ภายนอก
- ผลทดสอบล่าสุด:

```text
177 passed, 174 subtests
```

---

## State Payload ที่ยืนยันแล้ว

Top-level keys:

```text
schema
device_id
status
cargo_type
source
route
obstacle_distance
last
events
risk_map
```

Path สำหรับ Dashboard:

| ข้อมูล | Path |
|---|---|
| Mission status | `status` |
| Cargo type | `cargo_type` |
| Route | `route` |
| Obstacle distance | `obstacle_distance` |
| Surface class | `last.label` |
| Prediction confidence | `last.confidence` |
| Vibration risk | `last.risk` |
| Speed ratio | `last.decision.speed_ratio` |
| Safety action | `last.decision.action` |
| Current zone | `last.zone` |
| Zone risk memory | `risk_map` |

ตัวอย่าง State:

```text
status = MOVING
zone = A1
label = carpet
confidence = 0.580
risk = low
action = MOVE
speed_ratio = 1.0      (standard; fragile คืน 0.8 สำหรับหน้าต่างเดียวกัน)
progress = 0.1
```

State ปกติถูก retain ส่วน `error` และ `source_diagnostic` ไม่ retain ทุก path ในตารางด้านบนถูกยืนยันบน broker จริงแล้วใน `reports/demo_e2e_evidence.json`

---

## Sensor Studio state viewer

ระบบหลักและหน้าเว็บสาธิตทำงานแล้ว และเคยต่อ flow ขั้นต่ำ
`MQTT Subscriber → Message Viewer` ใน UI จริงจนเห็น retained state แล้ว
สิ่งที่ยังไม่มีคือไฟล์ preset ที่ export จาก Studio งานนี้ไม่ใช่ blocker ของ
Mission Protection Console หรือ Fleet Guardian

### Flow ขั้นต่ำ

```text
MQTT Subscriber
→ Message Viewer
```

การตั้งค่า:

```text
Host: 127.0.0.1
Port: 8883 (WebSocket, path `/`)
Topic: cargoshield/cargo-robot-01/state
```

### Flow ฝั่งคำสั่ง

**สร้างบน canvas ของ build นี้ไม่ได้** เพราะ Dashboard input widgets ถูกปิด คำสั่งทั้งหมดออกจาก
`webapp/` แทน (เสร็จแล้ว) รูปแบบด้านล่างเก็บไว้เผื่อ build ในอนาคตเปิดหมวด `dashboard` กลับมา:

```text
Dashboard Select
→ JSON Pack
→ MQTT Publisher
```

Topic:

```text
cargoshield/cargo-robot-01/command
```

### Controls ที่ต้องเพิ่ม (ถ้า Dashboard category กลับมา; ตอนนี้มีครบแล้วใน `webapp/`)

- Standard / Fragile
- Start
- Pause
- Reset
- Manual Resume
- Clear Obstacle
- Obstacle Distance
- Pickup Zone
- Destination Zone

### Dashboard Outputs ที่ต้องเพิ่ม

- Mission Status
- Cargo Type
- Route
- Current Zone
- Surface Class
- Confidence
- Vibration Risk
- Speed Ratio
- Safety Action
- Obstacle Distance
- Risk Map

### Digital Twin

`Model Viewer → Scene Output` **สร้างใน build นี้ไม่ได้** เพราะหมวด `scene` และ Stage 3D ถูกปิดในทุก profile
งานส่วนนี้ทำเสร็จแล้วในฝั่ง local webapp แทน (`webapp/scene.js`) ซึ่ง subscribe
`cargoshield/cargo-robot-01/state` ตัวเดียวกัน เปิดพร้อมกับ Flow บน canvas ได้ ทั้งสองจอเห็น engine
ตัวเดียวกันในเวลาเดียวกัน วิธีเปิดและวิธีอ่านฉากอยู่ใน `docs/CARGOSHIELD_VISUAL_FLOW_RUNBOOK.md`

หากในอนาคต Studio build ไหนเปิดหมวด `scene` กลับมา จึงค่อยเพิ่ม `Model Viewer → Scene Output` และต้อง
เลือกโมเดลจริงจาก Asset Manager แล้วทดสอบการเชื่อมจริงก่อนกล่าวอ้างว่าโมเดลเคลื่อนไหวตามหุ่นยนต์

### ไฟล์ที่ยังไม่มี

```text
visual-flow/cargoshield-edge.trn-flow-preset.json
```

ไฟล์นี้ต้อง Export จาก Sensor Studio จริง ไม่ควรสร้าง Schema ขึ้นมาเองจากการเดา

ตรวจสอบส่วนขยาย `terniondev.bitstream-studio-0.1.9` ที่ติดตั้งอยู่แล้วพบว่า **ไม่มีทางสร้างไฟล์นี้แบบอัตโนมัติ**:

- คำสั่ง VS Code ทั้ง 38 ตัวไม่มีคำสั่งใดสร้าง เปิด หรือ export flow graph (`exportLiveDataSdk` เป็นการ export npm package คนละเรื่อง)
- `exportFlowGraphJson` อยู่ในบันเดิลของ webview เท่านั้น (`out/webview/assets/SensorStudioApp-*.js`) และทำงานโดยแปลงสถานะ canvas ที่มีชีวิตอยู่เป็น `Blob` ให้ดาวน์โหลด ต้องมีคนคลิกบนผืนผ้าใบจริง
- CLI เดียวที่มาด้วยคือ `out/cli/download-free-pack.js` ซึ่งเป็นตัวโหลด asset

ดังนั้นขั้นตอนที่เหลือเป็นงานมือล้วน ทำตาม click-by-click ใน `docs/CARGOSHIELD_VISUAL_FLOW_RUNBOOK.md` ฝั่ง Python ที่ Flow ต้องคุยด้วยยืนยันครบแล้วใน `reports/demo_e2e_evidence.json`

---

## สิ่งที่ยังเป็น Prototype

- Obstacle Distance ยังมาจาก Slider หรือคำสั่งจำลอง (ตัว logic ตอบสนองทันที แต่ตัวเลขระยะยังเป็น input จำลอง)
- ยังไม่มี ToF หรือ Ultrasonic Sensor จริง
- ลำดับ 10 หน้าต่างในรอบสาธิตเป็น curated sequence ที่เลือกไว้ล่วงหน้า ไม่ใช่การสุ่มหรือการวิ่งจริงบนพื้น
- Zone ที่เดินระหว่างสาธิตมาจาก route ที่วางไว้ตอนเริ่ม ไม่ได้มาจากตำแหน่งจริงของหุ่นยนต์
- Visual Flow ขั้นต่ำ `MQTT Subscriber → Message Viewer` เคยทำงานใน UI จริงแล้ว
  แต่ยังไม่มีไฟล์ preset ที่ export และเก็บใน repository
- Digital Twin / 3D **บน canvas ของ Sensor Studio** สร้างใน build นี้ไม่ได้เลย เพราะหมวด `scene` และ Stage 3D ถูกปิดในทุก profile ฉาก 3D จึงอยู่ใน `webapp/scene.js` แทน ซึ่ง subscribe topic เดียวกัน
- ฉาก 3D เป็นการจำลองเชิงภาพ ไม่ใช่ตำแหน่งจริงของหุ่นยนต์ พิกัดโซนบนแผนผังเป็นเลย์เอาต์ที่วางเองให้ตรงกับเส้นเชื่อมของ `DEMO_GRAPH` ไม่ใช่พิกัดคลังสินค้าจริง และการเคลื่อนที่ระหว่างโซนเป็น interpolation เชิงภาพจาก `last.zone` กับ `last.progress` เท่านั้น
- ทดสอบเบราว์เซอร์แล้วเฉพาะ Chromium 149 บนเครื่องนี้ ยังไม่ได้ลอง Firefox หรือ Safari และยังไม่ได้เปิดผ่านคำสั่ง **Serve Web App Folder over HTTP** ของส่วนขยาย (ใช้ `python -m http.server` ซึ่งเสิร์ฟไฟล์ static ชุดเดียวกัน)
- ยังไม่มี SLAM
- ยังไม่มี Autonomous Avoidance ที่ทดสอบกับหุ่นยนต์จริง
- Risk Map เป็น Named-Zone Risk Map
- Route Cost เป็น Prototype Logic
- Live AI จาก BMI270 ยังไม่เปิดใช้
- ยังไม่ได้ยืนยันแกน หน่วย Sampling Rate Timestamp และ Window ให้ตรงกับ Dataset
- Secure Edge เช่น mTLS, Device Identity, OPTIGA Trust M, Secure Boot และ Protected Update ยังเป็นแผนต่อยอด
  — **มีเอกสารออกแบบแล้ว** ที่ [`docs/CARGOSHIELD_SECURE_EDGE_DESIGN.md`](../docs/CARGOSHIELD_SECURE_EDGE_DESIGN.md)
  แต่ยังไม่ได้ติดตั้งหรือทดสอบกับบอร์ดจริง

---

## Secure Edge Design (เอกสารออกแบบ ยังไม่ได้ deploy)

เอกสาร [`docs/CARGOSHIELD_SECURE_EDGE_DESIGN.md`](../docs/CARGOSHIELD_SECURE_EDGE_DESIGN.md)
ครอบคลุมเกณฑ์ 2.3 โดยแยกสถานะ **CURRENT / PROPOSED** ทุกหัวข้อ:

- **Assets และ Threat Model** — 8 assets, 10 ภัยคุกคามตาม STRIDE พร้อมระบุว่าอันไหนยังไม่มีการป้องกัน
- **Trust boundary** 5 เส้น (key↔MCU, บัส MCU↔OPTIGA, บอร์ด↔broker, broker↔backend,
  Safety Core↔Historian/API/Copilot) โดยมีเพียงเส้นสุดท้ายที่บังคับใช้จริงแล้วในโค้ดวันนี้
- **Device identity** — ECC P-256 สร้างในชิป, cert อายุ 90 วัน, key ที่ OID `0xE0F1`,
  cert ที่ `0xE0E1` (สอง OID นี้มาจากคู่มือ TESAIoT §6 ทีมยังไม่ได้ทดสอบเอง)
  ส่วน trust-anchor slot ยังเป็น candidate ที่ต้องยืนยัน
- **Secure provisioning bootstrap** — CSR ต้องเดินทางในช่อง Server-TLS ที่พิสูจน์ตัวตนด้วย
  one-time credential ก่อน แล้ว rotate/revoke credential นั้นทันทีที่ได้ device certificate
- **การป้องกันบัส MCU ↔ OPTIGA** — Shielded Connection + Platform Binding Secret เพราะ
  "private key non-exportable" ไม่ได้แปลว่าคำสั่งบนบัสถูกป้องกันจากการดัก แก้ หรือ replay
- **mTLS sequence** และ ACL ต่อ topic ต่ออุปกรณ์
- **Secure Boot chain** 5 ขั้น (รูปแบบที่ตั้งใจทำ ยังไม่ยืนยันว่าบอร์ดรองรับ)
- **Model integrity** — ต้องตรวจ digest **ก่อน** เรียก `joblib.load()` เพราะ joblib ใช้กลไก
  แบบ pickle โมเดลที่ถูกดัดแปลงจึงอาจนำไปสู่ arbitrary code execution ไม่ใช่แค่ prediction ผิด
- **Protected Update** แบบ A/B slot + anti-rollback counter + watchdog rollback
- **Failure policy** แยกสามชนิด — communication / identity / integrity พร้อมระบุว่าอุปกรณ์
  รับรู้ revocation ผ่านช่องทางใด และถ้าออฟไลน์จะยังไม่ทราบ
- **แผนทดสอบ E1–E16** และ **milestones M0–M10**

**สถานะจริง:** ยังไม่มีบอร์ดในมือ ยังไม่เคยเรียก API ของ OPTIGA ยังไม่เคยเชื่อมต่อแพลตฟอร์ม
และยังไม่มีเฟิร์มแวร์ของทีมบนบอร์ดใด MQTT ที่รันอยู่วันนี้เป็น plaintext บน loopback

การควบคุมที่เกี่ยวข้องกับเส้นทางฐานข้อมูลและ Maintenance Copilot มีสามชั้น และต้องไม่สรุปรวมกัน:

- **Historian** เป็น writer แบบ async ที่ใช้ role เขียนได้ (`cargo/historian.py:48`) จุดแข็งของมัน
  คือคิวมีขอบเขต ทิ้งและนับแทนที่จะบล็อก Safety Core — **ไม่ใช่ SELECT-only**
- **History API** เป็น HTTP **GET-only** (405 ทุก verb ที่เปลี่ยนข้อมูล) bind loopback
- **Maintenance Copilot** เป็นตัวเดียวที่ใช้ **SELECT-only PostgreSQL role**
  (`cargo/maintenance.py:65`) ร่วมกับ allowlist 7 คำถาม

ส่วน command authorization: **mission command path ใน `cargo/mqtt_service.py` ไม่มี
authentication เลย รวมทั้ง `manual_resume`** ส่วน `--command-token` เป็น optional shared
payload token ของ `cargo/fleet_service.py` ซึ่งคุมคำสั่งคนละชุด และเป็น application-level
command authorization ไม่ใช่ MQTT client authentication

**M6 (model integrity) แบ่งสองส่วนเพราะให้การรับประกันต่างกัน:** M6a เทียบ SHA-256 กับค่าที่เก็บ
ในเครื่อง ทำได้โดยไม่ต้องรอบอร์ด แต่ตรวจได้เพียง **accidental corruption** เท่านั้น — ผู้โจมตี
ที่เขียนไฟล์โมเดลได้ ก็เขียนไฟล์ digest ได้ด้วย ส่วน M6b คือ digest ที่มาจาก **signed manifest
หรือ trust anchor ที่แก้ไม่ได้** ซึ่งเป็นส่วนเดียวที่ป้องกัน malicious model replacement ได้จริง
และขึ้นกับ Secure Boot (M7) ทั้ง M6a และ M6b **ยังไม่ implement**

---

## จุดเด่นของโปรเจกต์

CargoShield AI ไม่ได้เป็นเพียงระบบตรวจสิ่งกีดขวางด้วย Threshold แต่รวมความสามารถต่อไปนี้ไว้ด้วยกัน:

- AI จำแนกสภาพพื้นผิว
- ประเมินความเสี่ยงต่อสินค้า
- ปรับพฤติกรรมตามประเภทสินค้า
- หยุดเมื่อ AI ไม่มั่นใจ
- จดจำพื้นที่เสี่ยง
- ใช้ข้อมูลเดิมช่วยวางเส้นทาง
- สื่อสารผ่าน MQTT
- แสดงผลผ่าน Mission Protection Console และ Fleet Guardian ใน `webapp/` *(เสร็จแล้ว)*
- รองรับการต่อยอดสู่ Secure Edge AI

---

## คำอธิบายแบบสั้น

> CargoShield AI คือ Prototype ระบบ AI สำหรับหุ่นยนต์ขนส่งสินค้า ปัจจุบันใช้ IMU windows ที่บันทึกไว้จาก validation split มา Replay เข้าโมเดล แล้วเผยแพร่ผลของแต่ละ window ผ่าน MQTT ให้ Mission Protection Console และ Fleet Guardian แสดงการตัดสินใจ ระบบยังไม่ได้วัดเซนเซอร์สดจากหุ่นยนต์จริง

Mission Protection Console และ Fleet Guardian ทำงานแล้ว ส่วน Sensor Studio 0.1.9 รองรับได้เพียง
subscriber/state viewer เพราะ dashboard และ scene category ถูกปิดใน build ที่ติดตั้ง

---

## สรุปสถานะปัจจุบัน

```text
CargoShield Engine       : ทำงานแล้ว
Dataset Replay           : ทำงานแล้ว (validation-only ไม่ใช่การวัดสด)
Surface AI               : ทำงานแล้ว
Cargo Policy             : ทำงานแล้ว
Route / Risk Map         : ทำงานแล้ว
Collision Logic          : ทำงานแล้ว
HOLDING / SAFE_STOP      : ทำงานแล้ว
MQTT Bridge              : ทำงานแล้ว
Obstacle Contract        : ทำงานแล้ว (ตอบสนองทันทีต่อ input จำลอง)
Demo Replay              : ทำงานแล้ว (10 หน้าต่าง ~10 วินาที)
End-to-End MQTT          : ตรวจผ่านแล้ว 14/14 (reports/demo_e2e_evidence.json)
Automated Tests          : 177 passed, 174 subtests
Mission Protection UI    : ทำงานแล้ว (Cargo Protection State + Risk/Action/Speed เป็นหัวข้อหลัก)
Fleet Guardian           : ทำงานแล้ว เป็นโมดูลภายใต้ CargoShield AI
Maintenance Assistant    : ทำงานแล้ว อ่านอย่างเดียว 7 คำถาม พร้อมแถวหลักฐาน
Hermes Provider          : ยังไม่เชื่อมต่อ (แสดงตามจริงบนหน้าเว็บ)
3D Operator Console      : ทำงานแล้ว ตรวจในเบราว์เซอร์จริงแล้ว (reports/webapp_ui_evidence.json)
Sensor Studio State View : ยังสร้าง/Export ด้วยมือได้เป็นงานเสริม
Visual Flow Export       : ยังไม่มี ต้องคลิก Export ใน Studio
Digital Twin บน Studio    : สร้างไม่ได้ใน build นี้ ใช้ webapp/scene.js แทน
Live BMI270 Inference    : ยังไม่เปิด
Secure Edge Design       : ทำแล้ว (CURRENT/PROPOSED + แผนทดสอบ)
Secure Edge Deployment   : ยังไม่ทำ / รอ milestone M1 และบอร์ดจริง
Proposal PDF             : ยังไม่มี
```

## เป้าหมายถัดไป

เป้าหมายหลักถัดไปคือทำ proposal PDF 5 หน้า A4 แนวตั้ง โดยแมปทุก claim กับหลักฐานและแยก
CURRENT/PROPOSED ให้ชัด หลังส่ง proposal หรือเมื่อมีบอร์ดจริง ค่อยทำ Secure Edge milestone M1
เพื่อยืนยัน root of trust/pinout/boot/update constraints และเก็บหน้าต่าง BMI270 จริงให้ตรงกับ
schema ของโมเดลก่อนเปิด Live Inference ส่วน Sensor Studio state viewer เป็นงานเสริมภายหลัง
