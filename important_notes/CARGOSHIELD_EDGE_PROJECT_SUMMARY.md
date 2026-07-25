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
- แสดงผลผ่าน Dashboard และ Digital Twin *(เป้าหมาย ยังไม่เสร็จ)*

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
127.0.0.1:1883
            ↓
Bitstream Sensor Studio
- Visual Flow
- Dashboard
- Controls
- Digital Twin
```

Python เป็นสมองหลัก ส่วน Sensor Studio ทำหน้าที่รับคำสั่งและแสดงสถานะ

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

ตัวอย่างคลาสจาก Dataset Demo:

- `hard_tiles_large_space`
- `hard_tiles`
- `tiled`
- `soft_pvc`

### Curated dataset demonstration sequence

รอบสาธิตใช้ชุด index คงที่ 10 หน้าต่างจากข้อมูลจริงในเครื่อง (`cargo.mqtt_service.DEMO_SEQUENCE`) เว้นระยะหน้าต่างละ `REPLAY_INTERVAL_S = 1.0` วินาที รวมประมาณ 10 วินาทีต่อรอบ ปรับจังหวะได้ด้วย `--interval` โดยไม่ต้องแก้ว่าใช้ข้อมูลหน้าต่างไหน

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

- Dataset Demo ใช้งานได้โดยไม่ต้องมีบอร์ด
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
- Obstacle controls ตอบสนองสดตาม contract ด้านบนแล้ว
- Replay เป็นชุดสาธิต 10 หน้าต่าง ~10 วินาที แสดงครบทั้ง MOVE, HOLD_UNCERTAIN และความต่างของ cargo policy
- ตรวจ end-to-end ผ่าน broker จริงด้วย `scripts/demo_e2e_check.py` เก็บหลักฐานไว้ที่ `reports/demo_e2e_evidence.json`
- ผลทดสอบล่าสุด:

```text
47 passed
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
label = hard_tiles_large_space
confidence = 0.705
risk = low
action = MOVE
speed_ratio = 0.8      (fragile; standard คืน 1.0 สำหรับหน้าต่างเดียวกัน)
progress = 0.1
```

State ปกติถูก retain ส่วน `error` และ `source_diagnostic` ไม่ retain ทุก path ในตารางด้านบนถูกยืนยันบน broker จริงแล้วใน `reports/demo_e2e_evidence.json`

---

## สิ่งที่ยังเหลือ

งานหลักที่ยังไม่เสร็จคือสร้าง Visual Flow และ Dashboard ใน Sensor Studio

### Flow ขั้นต่ำ

```text
MQTT Subscriber
→ Message Viewer
```

การตั้งค่า:

```text
Host: 127.0.0.1
Port: 1883
Topic: cargoshield/cargo-robot-01/state
```

### Flow ฝั่งคำสั่ง

```text
Dashboard Select
→ JSON Pack
→ MQTT Publisher
```

Topic:

```text
cargoshield/cargo-robot-01/command
```

### Controls ที่ต้องเพิ่ม

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

หลังจาก MQTT และ Dashboard ทำงานแล้ว จึงเพิ่ม:

```text
Model Viewer
→ Scene Output
```

ต้องเลือกโมเดลจริงจาก Asset Manager และทดสอบการเชื่อมจริงก่อนกล่าวอ้างว่าโมเดลเคลื่อนไหวตามหุ่นยนต์

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

- Obstacle Distance ยังมาจาก Slider หรือคำสั่งจำลอง (ตัว logic ตอบสนองสดแล้ว แต่ตัวเลขระยะยังเป็น input จำลอง)
- ยังไม่มี ToF หรือ Ultrasonic Sensor จริง
- ลำดับ 10 หน้าต่างในรอบสาธิตเป็น curated sequence ที่เลือกไว้ล่วงหน้า ไม่ใช่การสุ่มหรือการวิ่งจริงบนพื้น
- Zone ที่เดินระหว่างสาธิตมาจาก route ที่วางไว้ตอนเริ่ม ไม่ได้มาจากตำแหน่งจริงของหุ่นยนต์
- Visual Flow และ Digital Twin ยังไม่ได้สร้างและยังไม่เคยเห็นทำงานจริง จึงยังอ้างไม่ได้
- ยังไม่มี SLAM
- ยังไม่มี Autonomous Avoidance ที่ทดสอบกับหุ่นยนต์จริง
- Risk Map เป็น Named-Zone Risk Map
- Route Cost เป็น Prototype Logic
- Live AI จาก BMI270 ยังไม่เปิดใช้
- ยังไม่ได้ยืนยันแกน หน่วย Sampling Rate Timestamp และ Window ให้ตรงกับ Dataset
- 3D Digital Twin ยังไม่ได้เชื่อมกับ State จริง
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
- แสดงผลผ่าน Dashboard และ Digital Twin *(เป้าหมาย ยังไม่เสร็จ)*
- รองรับการต่อยอดสู่ Secure Edge AI

---

## คำอธิบายแบบสั้น

> CargoShield Edge คือระบบ AI สำหรับหุ่นยนต์ขนส่งสินค้า ซึ่งใช้ข้อมูลจาก IMU เพื่อจำแนกพื้นผิวและประเมินแรงสั่นสะเทือน จากนั้นปรับความเร็วและเส้นทางตามความเปราะบางของสินค้า พร้อมระบบชะลอ หยุดรอ และ Safe Stop เมื่อพบความเสี่ยง โดยเผยแพร่สถานะทั้งหมดผ่าน MQTT แบบเรียลไทม์ เพื่อให้ Dashboard และ Digital Twin ใน Sensor Studio นำไปแสดงผล

Dashboard และ Digital Twin เป็นเป้าหมายที่ยังต้องสร้าง ตอนนี้มีเฉพาะฝั่ง MQTT ที่ส่ง State ครบทุก Path แล้ว

---

## สรุปสถานะปัจจุบัน

```text
CargoShield Engine       : ทำงานแล้ว
Dataset Demo             : ทำงานแล้ว
Surface AI               : ทำงานแล้ว
Cargo Policy             : ทำงานแล้ว
Route / Risk Map         : ทำงานแล้ว
Collision Logic          : ทำงานแล้ว
HOLDING / SAFE_STOP      : ทำงานแล้ว
MQTT Bridge              : ทำงานแล้ว
Obstacle Contract        : ทำงานแล้ว (ตอบสนองสด)
Demo Replay              : ทำงานแล้ว (10 หน้าต่าง ~10 วินาที)
End-to-End MQTT          : ตรวจผ่านแล้ว (reports/demo_e2e_evidence.json)
Automated Tests          : 47 passed
Sensor Studio Dashboard  : ยังต้องสร้างด้วยมือ (เป้าหมายถัดไป)
Visual Flow Export       : ยังไม่มี ต้องคลิก Export ใน Studio (เป้าหมายถัดไป)
Digital Twin             : ยังต้องเชื่อม (เป้าหมายถัดไป)
Live BMI270 Inference    : ยังไม่เปิด
Secure Edge Deployment   : แผนต่อยอด
```

## เป้าหมายถัดไป

สร้าง Visual Flow ใน Sensor Studio ให้รับ State จาก Python แสดง Dashboard ส่งคำสั่งกลับไปยัง CargoShield Engine และ Export เป็นไฟล์ Flow จริงสำหรับใช้สาธิตต่อกรรมการ
