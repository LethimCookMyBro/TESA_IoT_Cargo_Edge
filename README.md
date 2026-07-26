# CargoShield Fleet Guardian

[English version](README%28EN%29.md)

ต้นแบบระบบดูแลหุ่นยนต์ขนส่งสินค้าแบบหลายตัวสำหรับ TESA IoT Cargo Edge ประกอบด้วย
AI จำแนกพื้นผิวจากหน้าต่างข้อมูล IMU ที่บันทึกไว้, Safety Core แบบ deterministic,
สัญญา MQTT แยกตามหุ่นยนต์, PostgreSQL Fleet Historian และหน้าเว็บ 3 มิติสำหรับสาธิต
Dataset Replay กับหน้า Fleet Intelligence สำหรับดูข้อมูลย้อนหลัง

> **สถานะข้อมูลปัจจุบัน:** ทุก record เป็น `DATASET` หรือ `SIMULATED` เท่านั้น
> ยังไม่มีการวัดสดจากบอร์ด, ตำแหน่งจริง, SLAM, เซนเซอร์ระยะ, มอเตอร์ หรือการเคลื่อนที่จริง

## สิ่งที่ระบบทำได้แล้ว

- Replay หน้าต่าง IMU จาก validation split เข้าโมเดลทีละหน้าต่างผ่าน Python Engine
- จำแนกพื้นผิว ประเมินความเสี่ยงการสั่น และตัดสินใจ `MOVE`, `SLOW_DOWN`,
  `HOLD_UNCERTAIN` หรือ `SAFE_STOP`
- ปรับนโยบายตามสินค้าทั่วไป/สินค้าเปราะบาง และจำความเสี่ยงรายโซนสำหรับวางเส้นทางรอบถัดไป
- แยก state ของหุ่นยนต์หลายตัวและตรวจข้อมูลซ้ำ ลำดับผิด ค่ากระโดด และค่าที่ไม่เป็นตัวเลข
- เก็บ telemetry, prediction, event และ mission ลง PostgreSQL ผ่าน queue ที่ไม่ขวาง Safety Core
- แสดง Dataset Replay ในคลังสินค้า Three.js และแสดงภาพรวมกองหุ่นยนต์/ประวัติผ่าน Fleet Intelligence
- เตรียมขอบเขต Maintenance Copilot แบบอ่านอย่างเดียว โดยไม่มีสิทธิ์สั่งหุ่นยนต์หรือแก้ Safety Core

## Dataset ถูกใช้อย่างไร

ชุดข้อมูลไม่ได้ใช้สำหรับ train เพียงอย่างเดียว แต่แบ่งตาม group โดยไม่ให้ทับกัน:

| Split | หน้าที่ |
| --- | --- |
| Train | ฝึก RandomForest และหาขอบเขต vibration risk |
| Validation | เลือก confidence threshold และเป็นแหล่งหน้าต่างสำหรับ Dataset Replay |
| Test | ประเมินผลสุดท้ายใน `reports/metrics.json` เท่านั้น |

Dataset Replay เป็นการป้อนข้อมูลที่บันทึกไว้เข้า pipeline ตามลำดับเวลาเพื่อสาธิตการตัดสินใจ
ไม่ใช่การวัดสด และไม่ใช่ผลประเมินจาก test split

## ติดตั้ง

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

ถ้าต้องสร้าง dataset/model artifacts ใหม่:

```powershell
.\.venv\Scripts\python.exe -m training.prepare_dataset
.\.venv\Scripts\python.exe -m training.train_baseline
.\.venv\Scripts\python.exe -m training.select_confidence
.\.venv\Scripts\python.exe -m training.evaluate_baseline
```

เริ่ม PostgreSQL Fleet Historian บน loopback:

```powershell
docker compose up -d
.\.venv\Scripts\python.exe -m cargo.db
```

ค่าการเชื่อมต่ออ่านจาก environment; คัดลอก `.env.example` เป็น `.env` เมื่อต้องการเปลี่ยนค่า

## เปิดระบบ

ต้องมี MQTT broker ที่ `127.0.0.1:1883` และ MQTT-over-WebSocket ที่ `127.0.0.1:8883`
(broker ของ Bitstream Studio ใช้ค่านี้ได้) จากนั้นเปิดแต่ละ service:

```powershell
# Engine สำหรับ Dataset Replay ของหุ่นยนต์หนึ่งตัว
.\.venv\Scripts\python.exe -m cargo.mqtt_service

# Fleet Guardian และ History API แบบอ่านอย่างเดียว
.\.venv\Scripts\python.exe -m cargo.fleet_service
.\.venv\Scripts\python.exe -m cargo.history_api --port 8099

# หน้าเว็บทั้งสองหน้า
.\.venv\Scripts\python.exe -m http.server 8080 --bind 127.0.0.1 --directory webapp
```

- Dataset Replay 3 มิติ: <http://127.0.0.1:8080/index.html>
- Fleet Intelligence: <http://127.0.0.1:8080/fleet.html>

ปุ่ม **เริ่ม Dataset Replay** ส่ง `{"action":"start"}` ไปที่
`cargoshield/cargo-robot-01/command` แล้ว replay 10 validation windows ภายในประมาณ 10 วินาที
Safe Stop จะ latch จนกว่าผู้ควบคุมจะกด `manual_resume`

## เดโมกองหุ่นยนต์

```powershell
.\.venv\Scripts\python.exe scripts\fleet_scenario.py
```

scenario นี้จำลองหุ่นยนต์สามตัวพร้อมกัน: ตัวปกติ, ตัวที่สะสมแรงสั่นและเกิด impact จน Safe Stop,
และตัวที่ส่งข้อมูลผิดปกติ พร้อมตัด PostgreSQL ชั่วคราวเพื่อพิสูจน์ว่า Safety Core ยังตัดสินใจต่อได้
หลักฐานอยู่ที่ `reports/fleet_scenario_evidence.json`

## ตรวจสอบ

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q cargo training scripts tests
.\.venv\Scripts\python.exe scripts\smoke_mqtt_flow.py --dataset-demo
.\.venv\Scripts\python.exe scripts\demo_e2e_check.py
.\.venv\Scripts\python.exe scripts\fleet_scenario.py
.\.venv\Scripts\python.exe scripts\webapp_ui_check.py --url "http://127.0.0.1:8080/?device=ui-verify"
.\.venv\Scripts\python.exe -m pip_audit -r requirements.txt
```

ผลล่าสุดที่ยืนยันบน checkout นี้: **131 tests + 111 subtests**, MQTT E2E **14/14**,
Fleet Scenario **12/12**, browser verification ผ่านโดยไม่มี console error และ `pip-audit`
ไม่พบช่องโหว่ที่รู้จัก ผล latency เป็นของ local simulator ไม่ใช่ประสิทธิภาพของบอร์ด

## เอกสารหลัก

| เอกสาร | เนื้อหา |
| --- | --- |
| [`docs/FLEET_GUARDIAN_FINAL_REPORT.md`](docs/FLEET_GUARDIAN_FINAL_REPORT.md) | สถานะปัจจุบัน สถาปัตยกรรม หลักฐาน และข้อห้ามในการอ้าง |
| [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md) | สิ่งที่ระบบยังทำไม่ได้หรือยังไม่ยืนยัน |
| [`docs/ML_EVALUATION.md`](docs/ML_EVALUATION.md) | วิธีแบ่งข้อมูล ผล test และ confidence threshold |
| [`docs/HARDWARE_EXPANSION_MATRIX.md`](docs/HARDWARE_EXPANSION_MATRIX.md) | หลักฐานที่ยังขาดก่อนต่อกล้อง ไมค์ ระยะ หรือมอเตอร์ |
| [`docs/HERMES_MAINTENANCE_COPILOT.md`](docs/HERMES_MAINTENANCE_COPILOT.md) | ขอบเขต Copilot แบบอ่านอย่างเดียว |
| [`docs/CARGOSHIELD_VISUAL_FLOW_RUNBOOK.md`](docs/CARGOSHIELD_VISUAL_FLOW_RUNBOOK.md) | MQTT/Bitstream Sensor Studio และข้อจำกัดของ build |
| [`docs/FLEET_GUARDIAN_PHASE0_BASELINE.md`](docs/FLEET_GUARDIAN_PHASE0_BASELINE.md) | หลักฐาน baseline ก่อนสร้าง Fleet Guardian (เอกสารประวัติ) |
