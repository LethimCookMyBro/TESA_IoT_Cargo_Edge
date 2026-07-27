import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { HeaderBar } from "../components/HeaderBar";

export const ProblemScene: React.FC = () => {
  const frame = useCurrentFrame();

  const card1Opacity = interpolate(frame, [15, 35], [0, 1], {
    extrapolateRight: "clamp",
  });
  const card2Opacity = interpolate(frame, [45, 65], [0, 1], {
    extrapolateRight: "clamp",
  });
  const card3Opacity = interpolate(frame, [75, 95], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ backgroundColor: "#0b0f19", color: "#ffffff" }}>
      <HeaderBar title="CargoShield AI — Problem Definition" badge="THE UNSEEN RISK" />

      {/* Main Grid Layout */}
      <div
        style={{
          position: "absolute",
          top: 130,
          left: 80,
          right: 80,
          bottom: 120,
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 40,
          alignItems: "center",
        }}
      >
        {/* Left Side: Captured Real Footage Card */}
        <div
          style={{
            position: "relative",
            width: "100%",
            height: "100%",
            maxHeight: 700,
            borderRadius: 16,
            overflow: "hidden",
            border: "1px solid rgba(0, 242, 254, 0.3)",
            boxShadow: "0 20px 50px rgba(0,0,0,0.6)",
          }}
        >
          <Img
            src={staticFile("assets/current-capture/03_mission_moving.png")}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
          <div
            style={{
              position: "absolute",
              bottom: 24,
              left: 24,
              right: 24,
              backgroundColor: "rgba(11, 15, 25, 0.9)",
              border: "1px solid rgba(239, 35, 60, 0.5)",
              borderRadius: 12,
              padding: "16px 24px",
            }}
          >
            <div style={{ color: "#ef233c", fontSize: 18, fontWeight: 700, fontFamily: "monospace" }}>
              ⚠️ CONVENTIONAL NAVIGATION LIMITATION
            </div>
            <div style={{ color: "#ffffff", fontSize: 24, fontWeight: 600, marginTop: 4 }}>
              หุ่นยนต์รู้เพียง "ตำแหน่งเป้าหมาย" แต่ไม่รู้ "ความเสี่ยงแรงสั่นสะเทือนต่อสินค้า"
            </div>
          </div>
        </div>

        {/* Right Side: Key Problem Statements */}
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          <div
            style={{
              opacity: card1Opacity,
              backgroundColor: "rgba(15, 23, 42, 0.8)",
              borderLeft: "6px solid #ef233c",
              borderRadius: "0 12px 12px 0",
              padding: "24px 32px",
              boxShadow: "0 10px 30px rgba(0,0,0,0.4)",
            }}
          >
            <h3 style={{ margin: 0, fontSize: 32, color: "#ffffff", fontWeight: 700 }}>
              1. สภาพพื้นผิวสร้างแรงสั่นสะเทือนต่างกัน
            </h3>
            <p style={{ margin: "8px 0 0", fontSize: 24, color: "#94a3b8", lineHeight: 1.4 }}>
              เส้นทางที่สั้นที่สุดอาจเป็นพื้นผิวขรุขระ รอยต่อกระเบื้อง หรือคอนกรีตหยาบ ซึ่งเพิ่มความเสี่ยงต่อสินค้า
            </p>
          </div>

          <div
            style={{
              opacity: card2Opacity,
              backgroundColor: "rgba(15, 23, 42, 0.8)",
              borderLeft: "6px solid #ffb703",
              borderRadius: "0 12px 12px 0",
              padding: "24px 32px",
              boxShadow: "0 10px 30px rgba(0,0,0,0.4)",
            }}
          >
            <h3 style={{ margin: 0, fontSize: 32, color: "#ffffff", fontWeight: 700 }}>
              2. สินค้าเปราะบางต้องการนโยบายเฉพาะ
            </h3>
            <p style={{ margin: "8px 0 0", fontSize: 24, color: "#94a3b8", lineHeight: 1.4 }}>
              สินค้าทั่วไปกับสินค้าเปราะบางไม่ควรเคลื่อนที่ด้วยความเร็วและเงื่อนไขความปลอดภัยเดียวกัน
            </p>
          </div>

          <div
            style={{
              opacity: card3Opacity,
              backgroundColor: "rgba(15, 23, 42, 0.8)",
              borderLeft: "6px solid #00f2fe",
              borderRadius: "0 12px 12px 0",
              padding: "24px 32px",
              boxShadow: "0 10px 30px rgba(0,0,0,0.4)",
            }}
          >
            <h3 style={{ margin: 0, fontSize: 32, color: "#ffffff", fontWeight: 700 }}>
              3. CargoShield AI เติมเต็มช่องว่างนี้
            </h3>
            <p style={{ margin: "8px 0 0", fontSize: 24, color: "#94a3b8", lineHeight: 1.4 }}>
              ทำหน้าที่เป็น Cargo Protection Layer แทรกระหว่างเซนเซอร์กับการตัดสินใจเคลื่อนที่ของหุ่นยนต์
            </p>
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
