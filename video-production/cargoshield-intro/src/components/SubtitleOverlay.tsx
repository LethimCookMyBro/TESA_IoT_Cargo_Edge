import React from "react";
import { interpolate, useCurrentFrame } from "remotion";

export interface SubtitleItem {
  id: number;
  startFrame: number;
  endFrame: number;
  text: string;
}

export const SUBTITLES: SubtitleItem[] = [
  {
    id: 1,
    startFrame: 15,
    endFrame: 174,
    text: "จากการขนส่งที่มองไม่เห็นความเสี่ยง สู่ CargoShield AI\nระบบปกป้องสินค้าสำหรับหุ่นยนต์ขนส่ง",
  },
  {
    id: 2,
    startFrame: 186,
    endFrame: 375,
    text: "การที่หุ่นยนต์ไปถึงจุดหมาย\nไม่ได้แปลว่าสินค้าได้รับการปกป้องระหว่างทาง",
  },
  {
    id: 3,
    startFrame: 384,
    endFrame: 585,
    text: "แรงสั่นสะเทือนและพื้นผิวที่แตกต่าง อาจสร้างความเสียหายต่อสินค้าเปราะบาง\nCargoShield AI จึงเพิ่มชั้นตัดสินใจประเมินความเสี่ยงต่อสินค้าโดยเฉพาะ",
  },
  {
    id: 4,
    startFrame: 606,
    endFrame: 855,
    text: "ระบบนำข้อมูล IMU เข้าสู่ Surface AI จำแนกพื้นผิว\nผ่าน Confidence Gate ประเมิน Vibration Risk และประมวลผลด้วย Cargo Policy",
  },
  {
    id: 5,
    startFrame: 864,
    endFrame: 1125,
    text: "โดย Safety Core เป็นผู้สั่งการเด็ดขาด\nและฐานข้อมูลอยู่นอก synchronous safety path",
  },
  {
    id: 6,
    startFrame: 1146,
    endFrame: 1395,
    text: "ใน Mission Protection Console เมื่อเลือกสินค้าเปราะบาง\nระบบจะปรับนโยบายความเร็วให้ระมัดระวังยิ่งขึ้น",
  },
  {
    id: 7,
    startFrame: 1404,
    endFrame: 1665,
    text: "หากโมเดล AI ไม่มั่นใจในผลจำแนก ระบบจะเข้าสู่ HOLD UNCERTAIN\nหยุดรอทันทีโดยไม่เดาสุ่ม",
  },
  {
    id: 8,
    startFrame: 1674,
    endFrame: 1995,
    text: "และเมื่อพบสิ่งกีดขวางหรือเหตุอันตราย ระบบจะ SAFE STOP\nล็อคการทำงานอย่างปลอดภัยจนกว่าผู้ควบคุมจะสั่งรีซูม",
  },
  {
    id: 9,
    startFrame: 2010,
    endFrame: 2244,
    text: "มุมมองกล้องรองรับ Overview, Follow และ Robot POV\nเพื่อติดตามภารกิจแบบเรียลไทม์",
  },
  {
    id: 10,
    startFrame: 2256,
    endFrame: 2505,
    text: "สำหรับผู้ดูแลระบบ Fleet Guardian ช่วยติดตามสถานะหุ่นยนต์หลายตัว\nบันทึก Safety Events และประวัติภารกิจย้อนหลัง",
  },
  {
    id: 11,
    startFrame: 2514,
    endFrame: 2805,
    text: "พร้อม Maintenance Assistant แบบ deterministic อ่านอย่างเดียว\nที่ให้มนุษย์เป็นผู้รับรอง โดย Hermes provider ยังไม่ได้เชื่อมต่อ",
  },
  {
    id: 12,
    startFrame: 2826,
    endFrame: 3045,
    text: "CargoShield ผ่านการทดสอบ Automated tests 177 รายการ\nMQTT E2E 14 รายการ และ Fleet scenario 12 รายการ",
  },
  {
    id: 13,
    startFrame: 3054,
    endFrame: 3225,
    text: "บน held-out dataset โมเดลทำ Accuracy ของหน้าต่างที่ยอมรับได้ 72.1%\nโดยเน้นหยุดปลอดภัยเมื่อไม่มั่นใจ",
  },
  {
    id: 14,
    startFrame: 3246,
    endFrame: 3465,
    text: "ปัจจุบัน CargoShield คือ Software Prototype บน workstation รันด้วย Dataset Replay\nส่วน Live BMI270, mTLS, OPTIGA Enclave และ Secure Boot คือสถาปัตยกรรมที่ออกแบบไว้",
  },
  {
    id: 15,
    startFrame: 3480,
    endFrame: 3594,
    text: "CargoShield AI\nProtect the cargo. Explain every decision.",
  },
];

export const SubtitleOverlay: React.FC = () => {
  const frame = useCurrentFrame();

  const activeSubtitle = SUBTITLES.find(
    (sub) => frame >= sub.startFrame && frame <= sub.endFrame
  );

  if (!activeSubtitle) return null;

  const fadeIn = interpolate(
    frame,
    [activeSubtitle.startFrame, activeSubtitle.startFrame + 8],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const fadeOut = interpolate(
    frame,
    [activeSubtitle.endFrame - 8, activeSubtitle.endFrame],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const opacity = Math.min(fadeIn, fadeOut);

  return (
    <div
      style={{
        position: "absolute",
        bottom: 50,
        left: 100,
        right: 100,
        display: "flex",
        justifyContent: "center",
        pointerEvents: "none",
        zIndex: 100,
        opacity,
      }}
    >
      <div
        style={{
          backgroundColor: "rgba(11, 15, 25, 0.92)",
          border: "1px solid rgba(0, 242, 254, 0.4)",
          boxShadow: "0 8px 32px rgba(0, 0, 0, 0.6)",
          borderRadius: 12,
          padding: "14px 32px",
          maxWidth: "85%",
          textAlign: "center",
        }}
      >
        <span
          style={{
            color: "#ffffff",
            fontSize: 32,
            lineHeight: 1.4,
            fontWeight: 600,
            whiteSpace: "pre-line",
            textShadow: "0 2px 4px rgba(0,0,0,0.8)",
            fontFamily: "Sarabun, Noto Sans Thai, sans-serif",
          }}
        >
          {activeSubtitle.text}
        </span>
      </div>
    </div>
  );
};
