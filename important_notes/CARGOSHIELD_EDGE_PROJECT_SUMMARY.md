# CargoShield Edge — สรุปสถานะโปรเจกต์

## โปรเจกต์นี้กำลังทำอะไร

**CargoShield Edge** คือระบบ AI สำหรับหุ่นยนต์บริการที่ขนส่งสินค้าในคลังสินค้า ห้าง โรงพยาบาล หรือโรงงาน

แนวคิดหลักคือ:

> หุ่นยนต์ไม่ได้สนใจเพียงว่าจะไปถึงปลายทางหรือไม่ แต่ต้องสนใจด้วยว่าสินค้าจะไปถึงโดยไม่เสียหายหรือไม่

ระบบใช้ข้อมูลการเคลื่อนไหวและแรงสั่นสะเทือนจาก IMU เพื่อ:

- จำแนกลักษณะพื้นผิวหรือรูปแบบการสั่น
- ประเมินความเสี่ยงต่อสินค้า
- ปรับความเร็วตามประเภทสินค้า
- เลือกเส้นทางที่เหมาะสม
- จดจำพื้นที่เสี่ยง
- ชะลอ หยุดรอ หรือหยุดฉุกเฉิน
- แสดงผลผ่าน 3D Dataset Replay Console และ Fleet Intelligence ใน `webapp/` *(เสร็จแล้ว)*
  พร้อมรองรับ Sensor Studio state viewer แบบเสริม

---

## สถาปัตยกรรมระบบ

```text
ข้อมูล IMU หรือ Dataset Replay
            ↓
Python CargoShield Engine
- AI จำแนกพื้นผิว
- ประเมิน vibration risk
- เลือก cargo policy
- คำนวณความเร็ว
- วางแผนเส้นทาง
- อัปเดต zone risk map
- ตัดสินใจ HOLD / SLOW DOWN / SAFE STOP
            ↓
Local MQTT Broker
127.0.0.1  TCP 1883 / WebSocket 8883
            ↓                    ↓
Bitstream Sensor Studio      webapp/ (3D Operator Console)
- Visual Flow (subscriber)   - Controls ทุกปุ่ม
- Display nodes              - Telemetry panels
                             - ฉากคลังสินค้า Three.js
```

Python เป็นสมองหลัก ปลายทางฝั่งแสดงผลมีสองทาง

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

คำสั่งจาก Sensor Studio ไป Python:

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
- **3D Operator Console ใน `webapp/` เสร็จแล้ว** ฉากคลังสินค้า Three.js แบบ procedural, โซน `A1..C2` จาก `DEMO_GRAPH` จริง, เส้นทางจาก `route.nodes`, heat overlay จาก `risk_map`, AGV พร้อมล้อและกล่องสินค้า (standard/fragile ต่างกันชัดเจน), obstacle marker ตามระยะจริง, orbit/pan/zoom + Reset camera
- เปิดหน้าเว็บจริงในเบราว์เซอร์และทดสอบครบทั้งลำดับสาธิตกับ broker จริงแล้ว ไม่มี console error เก็บหลักฐานที่ `reports/webapp_ui_evidence.json` และภาพที่ `reports/screenshots/`
- Three.js 0.180.0 (MIT) เก็บไว้ในเครื่องที่ `webapp/vendor/three/` ไม่ใช้ CDN ไม่มี asset ภายนอก
- ผลทดสอบล่าสุด:

```text
131 passed, 111 subtests
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

## งานเสริมที่ยังเหลือใน Sensor Studio

ระบบหลักและหน้าเว็บสาธิตทำงานแล้ว งานที่ยังเหลือใน Sensor Studio เป็น state viewer เสริม
ไม่ใช่ blocker ของ Dataset Replay Console หรือ Fleet Intelligence

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
- Visual Flow ยังไม่ได้สร้างและยังไม่เคยเห็นทำงานจริง จึงยังอ้างไม่ได้
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

---

## จุดเด่นของโปรเจกต์

CargoShield Edge ไม่ได้เป็นเพียงระบบตรวจสิ่งกีดขวางด้วย Threshold แต่รวมความสามารถต่อไปนี้ไว้ด้วยกัน:

- AI จำแนกสภาพพื้นผิว
- ประเมินความเสี่ยงต่อสินค้า
- ปรับพฤติกรรมตามประเภทสินค้า
- หยุดเมื่อ AI ไม่มั่นใจ
- จดจำพื้นที่เสี่ยง
- ใช้ข้อมูลเดิมช่วยวางเส้นทาง
- สื่อสารผ่าน MQTT
- แสดงผลผ่าน 3D Dataset Replay Console และ Fleet Intelligence ใน `webapp/` *(เสร็จแล้ว)*
- รองรับการต่อยอดสู่ Secure Edge AI

---

## คำอธิบายแบบสั้น

> CargoShield Edge คือ Prototype ระบบ AI สำหรับหุ่นยนต์ขนส่งสินค้า ปัจจุบันใช้ IMU windows ที่บันทึกไว้จาก validation split มา Replay เข้าโมเดล แล้วเผยแพร่ผลของแต่ละ window ผ่าน MQTT ให้ 3D Dataset Replay Console และ Fleet Intelligence แสดงการตัดสินใจ ระบบยังไม่ได้วัดเซนเซอร์สดจากหุ่นยนต์จริง

หน้าเว็บ 3 มิติและ Fleet Intelligence ทำงานแล้ว ส่วน Sensor Studio 0.1.9 รองรับได้เพียง
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
Automated Tests          : 131 passed, 111 subtests
3D Operator Console      : ทำงานแล้ว ตรวจในเบราว์เซอร์จริงแล้ว (reports/webapp_ui_evidence.json)
Sensor Studio State View : ยังสร้าง/Export ด้วยมือได้เป็นงานเสริม
Visual Flow Export       : ยังไม่มี ต้องคลิก Export ใน Studio
Digital Twin บน Studio    : สร้างไม่ได้ใน build นี้ ใช้ webapp/scene.js แทน
Live BMI270 Inference    : ยังไม่เปิด
Secure Edge Deployment   : แผนต่อยอด
```

## เป้าหมายถัดไป

เป้าหมายหลักถัดไปคือรับเอกสาร pinout/connector ของบอร์ดและเก็บหน้าต่าง BMI270 จริงให้ตรงกับ
schema ของโมเดล ก่อนเปิด Live Inference หรือต่อ range sensor และ motor ส่วน Sensor Studio
state viewer สามารถสร้างและ Export เพิ่มภายหลังได้ แต่ build นี้ส่งคำสั่งและทำ 3D บน canvas ไม่ได้
