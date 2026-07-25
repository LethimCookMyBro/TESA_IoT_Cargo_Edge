# คู่มือเทคนิคสำหรับผู้เข้าแข่งขัน

**TESAIoT Secure Edge AI Hackathon 2026 — Service Robotics**
แพลตฟอร์ม TESAIoT บนบอร์ด PSoC™ Edge E84 AI Kit พร้อมตัวอย่างการเชื่อมต่อ MQTT

---

## 1. ภาพรวมสถาปัตยกรรมระบบ

ระบบนิเวศ TESAIoT แบ่งเป็น 3 ชั้น ได้แก่:

1. **ชั้นอุปกรณ์ Edge** คือบอร์ด PSoC™ Edge E84 AI Kit ซึ่งรันเฟิร์มแวร์อ่านเซนเซอร์ ประมวลผล AI บนอุปกรณ์ และรักษาความปลอดภัยด้วยชิป OPTIGA™ Trust M
2. **ชั้นแพลตฟอร์ม TESAIoT** (tesaiot.com) รับข้อมูลผ่าน MQTT/HTTPS จัดการอุปกรณ์และใบรับรอง และแสดงผล Digital Twin แบบ 3D ผ่านส่วนขยาย Sensor Studio ใน VS Code
3. **ชั้น AI/MLOps** คือ X-brain Platform สำหรับทำ ETL, ติดป้ายข้อมูล (Label Studio) และฝึกโมเดล Machine Learning

---

## 2. รู้จักบอร์ด PSoC™ Edge E84 AI Kit (KIT_PSE84_AI)

| ส่วนประกอบ | รายละเอียด |
|---|---|
| หน่วยประมวลผล | Dual-core: Cortex-M55 (UI/แอปพลิเคชัน/Edge AI) + Cortex-M33 (Connectivity/ระบบ) โดย CM33 แบ่งโซน Secure / Non-Secure ด้วย ARM TrustZone |
| เซนเซอร์บนบอร์ด | Accelerometer & Gyroscope (BMI270), Magnetometer, Temperature/Humidity, Pressure พร้อมไลบรารี BSXLite (Bosch) สำหรับ Sensor Fusion หา Orientation |
| จอแสดงผล | จอสัมผัส 4.3 นิ้ว (AI Kit) รองรับ LVGL 9.2.0 พร้อม UI Theme/Layout ของ TESA และสคริปต์สร้างฟอนต์ภาษาไทย |
| เสียง | I2S + Audio Codec TLV320DAC3100 (ดูตัวอย่างโปรเจกต์ DoReMi) |
| ความปลอดภัย | ชิป OPTIGA™ Trust M เก็บกุญแจ ECC P-256 ในฮาร์ดแวร์ รองรับ CSR, mTLS และ Protected Update |
| การเชื่อมต่อ | WiFi, BLE (GATT), USB Serial (สตรีมข้อมูลเข้า Sensor Studio ที่ 115200 baud) |

---

## 3. เครื่องมือที่ต้องเตรียม

- Visual Studio Code + ส่วนขยาย TESA Digital Twin (Sensor Studio)
- Node.js 18 ขึ้นไป (สำหรับ T3D CLI ติดตั้ง CA Certificate)
- ModusToolbox™ + toolchain GCC_ARM สำหรับพัฒนาเฟิร์มแวร์ (จำเป็น: ไลบรารี BSXLite รองรับเฉพาะ GCC_ARM)
- Python 3.10+ (ติดตั้ง `paho-mqtt` สำหรับทดสอบ MQTT) และ `mosquitto-clients` (ทางเลือก)
- Docker + Docker Compose (หากต้องการรัน X-brain ETL/Label Studio ในเครื่อง)
- ซอร์สโค้ดและเอกสารทั้งหมด: `github.com/TESA-AIoT-Platform`

---

## 4. เริ่มต้นเร็วที่สุด: Digital Twin Sensor Studio

1. ดาวน์โหลดเฟิร์มแวร์ `.hex` ล่าสุดจากหน้า Releases ของ repo `TESAIoT_Firmware_for_DigitalTwin_Sensor_Studio` แล้วตรวจสอบไฟล์กับ `SHA256SUMS.txt`
2. แฟลชลงบอร์ด KIT_PSE84_AI ผ่าน USB ด้วยโปรแกรมเมอร์ของ TESAIoT
3. ติดตั้งส่วนขยาย TESA Digital Twin ใน VS Code (จาก Marketplace หรือไฟล์ VSIX)
4. รันคำสั่ง **"TERNION: Open Sensor Studio"** เปิด Serial Bridge เลือกพอร์ตของบอร์ดที่ 115200 baud
5. ข้อมูลเซนเซอร์ทุกตัวจะสตรีมแบบเรียลไทม์เข้าสู่มุมมอง 3D ทันที (โปรโตคอล TERNION BitStream)

สำหรับโหมดเชื่อมต่อคลาวด์ของ Digital Twin ให้ทำเพิ่ม 2 ขั้น: ติดตั้ง CA Certificate (ผ่าน T3D CLI) และตั้งค่า Credentials ในส่วนขยาย โดยใช้ **Host:** `mqtt.tesaiot.com`, **Port:** `8085` (TLS/WSS), **Username** = Device ID และ **Password** จากหน้า Device Management ของแพลตฟอร์ม จากนั้นกด Validate Connection ให้ขึ้นสถานะ Connected

---

## 5. การเชื่อมต่อ MQTT กับ TESAIoT Platform

### 5.1 ขั้นตอนขอ Credentials

1. เข้าสู่ระบบที่ `admin.tesaiot.com` แล้วสร้างอุปกรณ์ใหม่ในเมนู Device Management (เลือกโหมด Server-TLS สำหรับเริ่มต้น)
2. ดาวน์โหลด Credential Bundle ซึ่งประกอบด้วย `ca-chain.pem`, `mqtt-credentials.txt`, `mqtt_client_config.h` และโฟลเดอร์ `telemetry/` (โค้ด C สร้างอัตโนมัติตาม Data Schema ของอุปกรณ์)
3. กด Reset/Regenerate ในแท็บ Credentials เพื่อรับ Password (ระบบแสดงเพียงครั้งเดียว ให้บันทึกไว้ทันที)

### 5.2 ค่าคอนฟิกหลัก (โหมด Server-TLS)

| รายการ | ค่า |
|---|---|
| Broker | `mqtts://mqtt.tesaiot.com:8884` |
| การยืนยันตัวตน | Server-TLS: อุปกรณ์ตรวจสอบเซิร์ฟเวอร์ด้วย `ca-chain.pem` แล้วล็อกอินด้วย Username = Device ID (UUID 36 ตัวอักษร) + Password |
| Client ID | ใช้ Device ID (ต้องไม่ซ้ำกันต่อหนึ่งการเชื่อมต่อ) |
| Topic ส่งข้อมูล (Publish) | `device/{DEVICE_ID}/telemetry` และ `device/{DEVICE_ID}/telemetry/sensor` |
| Topic รับคำสั่ง (Subscribe) | `device/{DEVICE_ID}/commands/#` |
| QoS / Keep-alive | QoS 1 (แนะนำ), Keep-alive 180 วินาที, Timeout 10 วินาที |
| Payload | JSON ตาม Data Schema เช่น `{"timestamp":"2026-07-21T09:00:00Z","value":25.4}` |
| โหมดความปลอดภัยสูง | mTLS ด้วยใบรับรองอุปกรณ์จาก OPTIGA™ Trust M (ดูหัวข้อ 6) — Digital Twin extension ใช้พอร์ต 8085 (TLS/WSS) |

### 5.3 ตัวอย่างที่ 1 — Python (paho-mqtt): Publish telemetry + รับคำสั่ง

ติดตั้งไลบรารีก่อนด้วย `pip install paho-mqtt` แล้ววางไฟล์ `ca-chain.pem` ไว้โฟลเดอร์เดียวกับสคริปต์

```python
import ssl, json, time
import paho.mqtt.client as mqtt

DEVICE_ID = "<YOUR-DEVICE-ID>"   # UUID จาก Device Management
PASSWORD = "<YOUR-PASSWORD>"     # จากปุ่ม Reset ในแท็บ Credentials
BROKER, PORT = "mqtt.tesaiot.com", 8884
TOPIC_TELEMETRY = f"device/{DEVICE_ID}/telemetry"
TOPIC_COMMANDS = f"device/{DEVICE_ID}/commands/#"

def on_connect(client, userdata, flags, rc, properties=None):
    print("Connected, rc =", rc)
    client.subscribe(TOPIC_COMMANDS, qos=1)  # รับคำสั่งจากแพลตฟอร์ม

def on_message(client, userdata, msg):
    print("CMD:", msg.topic, "->", msg.payload.decode())

client = mqtt.Client(client_id=DEVICE_ID, protocol=mqtt.MQTTv311)
client.username_pw_set(DEVICE_ID, PASSWORD)
client.tls_set(ca_certs="ca-chain.pem",
               tls_version=ssl.PROTOCOL_TLS_CLIENT)  # Server-TLS
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, PORT, keepalive=180)
client.loop_start()

while True:  # ส่ง telemetry ทุก 5 วินาที
    payload = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "value": 25.4  # แทนด้วยค่าจากเซนเซอร์จริง
    }
    client.publish(TOPIC_TELEMETRY, json.dumps(payload), qos=1)
    time.sleep(5)
```

### 5.4 ตัวอย่างที่ 2 — ทดสอบเร็วด้วย mosquitto CLI

```bash
# ส่งข้อมูล telemetry 1 ข้อความ
mosquitto_pub -h mqtt.tesaiot.com -p 8884 --cafile ca-chain.pem \
  -u "<DEVICE_ID>" -P "<PASSWORD>" -i "<DEVICE_ID>" -q 1 \
  -t "device/<DEVICE_ID>/telemetry" \
  -m '{"timestamp":"2026-07-21T09:00:00Z","value":25.4}'

# เฝ้าฟังคำสั่งที่แพลตฟอร์มส่งลงมา
mosquitto_sub -h mqtt.tesaiot.com -p 8884 --cafile ca-chain.pem \
  -u "<DEVICE_ID>" -P "<PASSWORD>" -i "<DEVICE_ID>-sub" -q 1 \
  -t "device/<DEVICE_ID>/commands/#" -v
```

### 5.5 ตัวอย่างที่ 3 — ฝั่งเฟิร์มแวร์ C บนบอร์ด (ModusToolbox)

Credential Bundle มีไฟล์ `mqtt_client_config.h` ที่ตั้งค่าให้ครบแล้ว เพียงนำไปแทนที่ในโปรเจกต์ ค่าหลักที่ควรรู้:

```c
#define DEVICE_ID "<YOUR-DEVICE-ID>"
#define MQTT_BROKER_ADDRESS "mqtt.tesaiot.com"
#define MQTT_PORT 8884                    /* Server-TLS */
#define MQTT_SECURE_CONNECTION ( 1 )
#define MQTT_ENABLE_MUTUAL_AUTH ( 0 )      /* 1 เมื่อใช้ mTLS + OPTIGA */
#define MQTT_USERNAME DEVICE_ID
#define MQTT_PUB_TOPIC "device/" DEVICE_ID "/telemetry"
#define MQTT_SUB_TOPIC "device/" DEVICE_ID "/commands/#"
#define MQTT_MESSAGES_QOS ( 1 )
#define MQTT_KEEP_ALIVE_SECONDS ( 180 )
```

ส่วนการแปลงค่าจากเซนเซอร์เป็น JSON ให้ใช้โค้ดในโฟลเดอร์ `telemetry/` ที่แพลตฟอร์มสร้างให้ตาม Data Schema:

```c
#include "data_telemetry.h"

telemetry_data_t data;
char json_buf[TELEMETRY_MAX_JSON_SIZE];

telemetry_init(&data);
TELEMETRY_SET_TIMESTAMP(&data, iso8601_now());
TELEMETRY_SET_VALUE(&data, read_temperature());  /* ค่าจากเซนเซอร์ */

int32_t len = telemetry_to_json(&data, json_buf, sizeof(json_buf));
if (len > 0) {
    mqtt_publish(MQTT_PUB_TOPIC, json_buf, len);  /* QoS 1 */
}
```

---

## 6. Secure Edge ด้วย OPTIGA™ Trust M (คะแนนเกณฑ์ 2.3)

เมื่อพร้อมยกระดับจาก Server-TLS ไปสู่ mTLS เต็มรูปแบบ TESAIoT SDK (`tesaiot.h` เวอร์ชัน 2.8.0) มีเวิร์กโฟลว์ให้ครบ กุญแจส่วนตัวถูกสร้างและเก็บในชิป OPTIGA โดยไม่เคยออกจากฮาร์ดแวร์:

1. สร้างคู่กุญแจ ECC P-256 ในชิป เก็บที่ OID `0xE0F1` ด้วย `tesaiot_optiga_generate_keypair()`
2. สร้าง CSR ที่เซ็นโดยชิปด้วย `tesaiot_optiga_generate_csr()` แล้วส่งไปยังแพลตฟอร์มผ่าน topic `device/{ID}/commands/csr`
3. แพลตฟอร์มออกใบรับรองอุปกรณ์ เก็บที่ OID `0xE0E1` จากนั้นเชื่อมต่อ MQTT แบบ mutual TLS (ตั้ง `MQTT_ENABLE_MUTUAL_AUTH = 1`)
4. ต่ออายุใบรับรองด้วย Protected Update: แพลตฟอร์มส่ง manifest ที่ลงลายเซ็น + payload เข้ารหัส ผ่าน topic `commands/protected_update`

**แนวคิดที่ควรเขียนในเอกสารเทคนิคของทีม:** Root of Trust อยู่ในฮาร์ดแวร์, การแยกโซน Secure/Non-Secure บน CM33 (TrustZone), และช่องทางสื่อสารทุกเส้นเข้ารหัส TLS ตลอดทาง

---

## 7. ต่อยอดสู่ X-brain (AI / MLOps)

- ส่งข้อมูลแบบ HTTPS (ทางเลือกแทน MQTT): POST ไปที่ `https://tesaiot.com:9444` ด้วย API Key (Server-TLS) — ดูตัวอย่าง `main.c` ใน repo `X-brain_API-Integration`
- ดึงข้อมูลฝั่งแอปพลิเคชัน: REST API ที่ `admin.tesaiot.com/api/v1/external` และเรียลไทม์ผ่าน `wss://admin.tesaiot.com/ws/telemetry` (ตัวอย่าง Python CLI ใน `app.py`)
- ETL: Apache Airflow DAG ตัวอย่าง (`tesaiot.py`) ดึงข้อมูลจากแพลตฟอร์ม แปลงเป็น Parquet โหลดเข้า PostgreSQL
- ติดป้ายข้อมูลเซนเซอร์ด้วย Label Studio (`docker compose up -d` เปิดที่พอร์ต 8085) ก่อนนำไปฝึกโมเดล แล้ว deploy กลับสู่ Edge

---

## 8. เช็กลิสต์และข้อควรระวัง

- Firmware Stack ยังเป็นเวอร์ชัน Alpha และอัปเดตบ่อย — ดึงโค้ดล่าสุดก่อนเริ่มงานทุกครั้ง
- BSXLite (Sensor Fusion) คอมไพล์ได้เฉพาะ toolchain GCC_ARM เท่านั้น
- Password/API Key แสดงเพียงครั้งเดียวตอน Reset — บันทึกทันทีและห้าม commit ลง Git เด็ดขาด
- Client ID ต้องไม่ซ้ำ: หากเปิดหลายการเชื่อมต่อพร้อมกัน ให้ต่อท้ายด้วย suffix เช่น `-sub`, `-dashboard`
- ทดสอบลำดับจากง่ายไปยาก: Sensor Studio (USB) → mosquitto/Python (Server-TLS) → เฟิร์มแวร์ C → mTLS + OPTIGA
- ไลบรารี `libtesaiot.a` ผูกกับชิป OPTIGA เป็นรายอุปกรณ์ (hardware-bound license) — ติดต่อ `support@tesaiot.com` หากมีปัญหา

---

## 9. แหล่งอ้างอิง

- เฟิร์มแวร์ Digital Twin: `github.com/TESA-AIoT-Platform/TESAIoT_Firmware_for_DigitalTwin_Sensor_Studio`
- Firmware Stack + ตัวอย่างทั้งหมด: `github.com/TESA-AIoT-Platform/TESAIoT_Firmware_Stack_Alpha_Examples`
- การเชื่อมต่อ Device/Application: `github.com/TESA-AIoT-Platform/X-brain_API-Integration`
- แพลตฟอร์มและเอกสาร: `admin.tesaiot.com` | `docs.tesaiot.com`

> **หมายเหตุ:** ค่าคอนฟิกในเอกสารนี้อ้างอิงจากซอร์สโค้ดและ Credential Bundle จริงของแพลตฟอร์ม ณ เดือนกรกฎาคม 2026 โปรดตรวจสอบกับไฟล์ในบันเดิลของอุปกรณ์ตนเองอีกครั้งก่อนใช้งาน
