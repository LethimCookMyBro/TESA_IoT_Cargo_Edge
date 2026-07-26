# TESAIoT Secure Edge AI Hackathon 2026 — สรุปข้อมูลสำคัญ

อัปเดตจากคู่มือ Hackathon และการตรวจ Bitstream Studio ในเครื่อง วันที่ 16 กรกฎาคม 2026

เอกสารต้นทาง: `TESAIoT-Secure-Edge-AI-Hackathon-2026.pdf` (ไฟล์ต้นทางอยู่นอก repository
จึงไม่ใส่ลิงก์ local ที่เปิดได้เฉพาะเครื่องเดิม)

## 1. โจทย์การแข่งขัน

- Theme ปี 2026: **Service Robotics**
- ใช้ AI, IoT, Embedded Systems และ Edge AI เพื่อแก้ปัญหางานบริการ
- ไม่จำเป็นต้องสร้างหุ่นยนต์ทั้งตัว ผลงานอาจเป็นระบบตรวจจับ, ระบบติดตาม, Dashboard, AI Agent หรือ Digital Twin
- ตัวอย่างพื้นที่ใช้งาน: โรงพยาบาล, โรงแรม, โรงงาน, คลังสินค้า, เกษตร และการดูแลผู้สูงอายุ

## 2. เส้นทางการแข่งขัน

1. สมัครผ่าน Maker Hub และเลือกภูมิภาค
2. เข้า Regional Pre-Hackathon Roadshow — Workshop 1 วัน
3. พัฒนา Prototype/Demo ต่อ 3 วัน และส่งผลงานออนไลน์
4. ทีมที่ผ่านเข้ารอบไปแข่ง National Final

### กำหนดการ Workshop

| ภูมิภาค | วันที่ | สถานที่ |
|---|---:|---|
| เหนือ | 17 ก.ค. 2569 | มทร.ล้านนา ดอยสะเก็ด |
| กลาง | 22 ก.ค. 2569 | มทร.ธัญบุรี ศูนย์คลองหก |
| ตะวันออกเฉียงเหนือ | 24 ก.ค. 2569 | มหาวิทยาลัยขอนแก่น |
| ตะวันออก | 25 ก.ค. 2569 | มหาวิทยาลัยบูรพา |
| กลาง | 27 ก.ค. 2569 | มหาวิทยาลัยสยาม |
| ใต้ | 31 ก.ค. 2569 | มหาวิทยาลัยวลัยลักษณ์ |

## 3. สิ่งที่จะได้ทำใน Workshop

### ช่วงเช้า

- รู้จัก TESAIoT Platform และ Development Kit
- ติดตั้งโปรแกรม
- ทดลอง Hardware และเขียนโปรแกรม
- อ่านค่าจาก Sensor
- ดูตัวอย่างการประยุกต์ AI + IoT

### ช่วงบ่าย

- วิเคราะห์โจทย์และทำ Design Thinking
- Brainstorm แนวคิดทีม
- ปรึกษา Mentor
- วางแผน Prototype/Demo ที่จะพัฒนาต่อใน 3 วัน

## 4. สิ่งที่ต้องเตรียม

- Notebook ส่วนตัว
- รองรับ Windows, macOS หรือ Linux
- ติดตั้งโปรแกรมและดูคู่มือ/วิดีโอล่วงหน้า
- ไม่จำเป็นต้องมีบอร์ดเอง โครงการมี TESAIoT Development Kit ให้ยืมในวัน Workshop

หลังคืนบอร์ดแล้ว ยังพัฒนาต่อด้วย Simulation และตัวอย่างโค้ดบน GitHub ได้

## 5. Bitstream Studio คืออะไร

Bitstream Studio เป็น **VS Code extension** สำหรับ:

- ดูข้อมูล Sensor แบบสด
- ทดลองระบบผ่าน Simulator โดยไม่ต้องมีบอร์ด
- เชื่อม TESAIoT PSoC Edge DevKit ผ่าน USB/UART
- เปิด Sensor Telemetry และ Sensor Studio
- ส่งข้อมูลต่อให้ Web Dashboard และ MQTT examples

มันไม่ใช่โปรแกรม standalone; ต้องเปิดผ่าน VS Code หรือ Cursor

## 6. วิธีเปิดใช้งาน

1. เปิดโฟลเดอร์ `TESAIoT_Hackathon-main` ใน VS Code
2. กด `Ctrl+Shift+P`
3. เลือก `Open Bitstream Studio`
4. เปิด `Sensor Telemetry` หรือ `Sensor Studio`
5. เลือกโหมด:
   - **Simulator** — ไม่มีบอร์ด
   - **Bitstream** — ใช้ DevKit จริง

### สถานะที่ตรวจพบในเครื่องนี้

- Bitstream Studio ติดตั้งแล้ว: `TERNIONDEV.bitstream-studio@0.1.9`
- VS Code: `1.129.0`
- ไม่มี COM port และยังไม่พบ DevKit
- Extension เปิด embedded Virt MCU simulator และส่งข้อมูลจำลองได้จริง
- Backend ที่ใช้งาน:
  - WebSocket telemetry provider: `ws://127.0.0.1:9997`
  - WebSocket broker: `ws://127.0.0.1:9998`
  - Model loader broker: `ws://127.0.0.1:9999`

## 7. Sensor ที่สำคัญ

| Sensor | ข้อมูลหลัก | ตัวอย่างงาน |
|---|---|---|
| BMI270 | Accel, Gyro, อุณหภูมิ, orientation | ตรวจการเคลื่อนไหว/การล้ม |
| BMM350 | Magnetometer, อุณหภูมิ | ทิศทาง/เข็มทิศ |
| SHT40 | อุณหภูมิ, ความชื้น | ห้องพัก/ผู้สูงอายุ/โรงงาน |
| DPS368 | ความดัน, อุณหภูมิ | สภาพแวดล้อม/ระบบตรวจวัด |

## 8. ตัวอย่าง Dashboard

หน้าเว็บตัวอย่างอยู่ใน `web-app/`:

- `ex01`–`ex04`: ทดลอง Sensor แยกตัว
- `ex05`: Artificial Horizon จาก BMI270
- `ex06`: Dashboard รวมทุก Sensor
- `ex08`: ตรวจสถานะการเชื่อมต่อ
- `ex09`–`ex15`: MQTT subscriber, publisher, wildcard, QoS และ Dashboard

ตัวอย่างที่เปิดทดสอบในเครื่อง:

[เปิด ex06 Dashboard](http://127.0.0.1:8899/ex06_dashboard.html)

ถ้าเปิดเองจาก VS Code ให้ใช้คำสั่ง `Serve Web App Folder over HTTP` แล้วเลือกโฟลเดอร์ `web-app`

## 9. ถ้าใช้บอร์ดจริง

- ใช้ VSIX และ firmware HEX เวอร์ชันเดียวกัน เช่น `0.1.9` คู่กับ `0.1.9`
- Flash ไฟล์ `hex/tesaiot-bitstream-0.1.9.hex`
- เลือก COM port ใน Bitstream Studio
- Baud rate: `921600`
- ถ้าไม่พบ COM port ให้ถอดเสียบ USB ใหม่ ตรวจสาย และติดตั้ง KitProg3 driver บน Windows

## 10. แนวคิดทำ Prototype ที่เข้ากับโจทย์

ทางที่ทำได้เร็วภายใน 3 วัน:

1. เลือกปัญหางานบริการหนึ่งปัญหา
2. ใช้ Sensor เพียง 1–2 ตัวเป็นหลัก
3. ทำ Dashboard แสดงสถานะและแจ้งเตือน
4. เพิ่มกติกา AI/Edge AI ที่อธิบายได้
5. ทำ Demo flow ให้เห็น input → วิเคราะห์ → action ชัดเจน

ตัวอย่างที่เหมาะกับอุปกรณ์ชุดนี้:

- ระบบเตือนผู้สูงอายุล้มหรือเคลื่อนไหวผิดปกติด้วย BMI270
- ระบบตรวจสภาพห้องพักด้วย SHT40 และ DPS368
- ระบบติดตามทิศทาง/การเคลื่อนที่ของอุปกรณ์บริการด้วย BMI270 + BMM350

## 11. Troubleshooting สั้น ๆ

| อาการ | วิธีแก้ |
|---|---|
| Panel ว่าง | `Bitstream Studio: Reload Webview` หรือ `Developer: Reload Window` |
| ไม่มีข้อมูลใน Simulator | ตรวจว่าเลือก `Simulator` และ backend ยังทำงาน |
| ไม่มีข้อมูลจากบอร์ด | ตรวจ COM, baud `921600`, firmware/VSIX ต้องตรงรุ่น |
| Web Dashboard ว่าง | เปิด Bitstream Studio ก่อน และเปิดผ่าน HTTP ไม่ใช่ดับเบิลคลิกไฟล์ HTML |
| MQTT ตัวอย่างไม่ทำงาน | เริ่ม broker จากเมนู `Server → Start broker` ก่อน |

## 12. ลิงก์สำคัญ

- สมัคร: <https://maker-hub.net>
- GitHub: <https://github.com/drsanti/TESAIoT_Hackathon>
- Repo ในเครื่อง: `C:\Users\User\Downloads\arjan_pomjapaipattaya\TESAIoT_Hackathon-main`

## 13. ข้อสังเกตไฟล์ใน repo

ไฟล์ `vsix/bitstream-studio-0.1.9.vsix` ใน checkout นี้เป็น Git LFS pointer ไม่ใช่ตัวติดตั้งจริง จึงไม่ควรใช้ไฟล์ 134 bytes นี้ติดตั้งโดยตรง การติดตั้งในเครื่องปัจจุบันสำเร็จแล้วและเป็น extension เวอร์ชัน `0.1.9`
