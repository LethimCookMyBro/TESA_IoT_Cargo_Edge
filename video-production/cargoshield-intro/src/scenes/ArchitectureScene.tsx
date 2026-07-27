import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { HeaderBar } from "../components/HeaderBar";

export const ArchitectureScene: React.FC = () => {
  const frame = useCurrentFrame();

  // Sequential animation steps for pipeline blocks
  const step1 = interpolate(frame, [10, 25], [0, 1], { extrapolateRight: "clamp" });
  const step2 = interpolate(frame, [30, 45], [0, 1], { extrapolateRight: "clamp" });
  const step3 = interpolate(frame, [50, 65], [0, 1], { extrapolateRight: "clamp" });
  const step4 = interpolate(frame, [70, 85], [0, 1], { extrapolateRight: "clamp" });
  const step5 = interpolate(frame, [90, 105], [0, 1], { extrapolateRight: "clamp" });

  const noteOpacity = interpolate(frame, [115, 135], [0, 1], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ backgroundColor: "#0b0f19", color: "#ffffff" }}>
      <HeaderBar title="CargoShield AI — System Architecture" badge="PROTECTION PIPELINE" />

      <div
        style={{
          position: "absolute",
          top: 140,
          left: 80,
          right: 80,
          bottom: 120,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "space-around",
        }}
      >
        {/* Title / Header */}
        <div style={{ textAlign: "center" }}>
          <h2
            style={{
              margin: 0,
              fontSize: 48,
              fontWeight: 800,
              color: "#ffffff",
              fontFamily: "Sarabun, sans-serif",
            }}
          >
            สถาปัตยกรรมและการไหลของข้อมูลความปลอดภัย
          </h2>
          <p style={{ margin: "8px 0 0", fontSize: 24, color: "#94a3b8" }}>
            ข้อมูล IMU 128×6 ➔ AI จำแนก ➔ Confidence Gate ➔ Safety Core สั่งการเด็ดขาด
          </p>
        </div>

        {/* Pipeline Nodes Flow */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 16,
            width: "100%",
          }}
        >
          {/* Node 1: IMU Window */}
          <div
            style={{
              opacity: step1,
              backgroundColor: "rgba(15, 23, 42, 0.9)",
              border: "2px solid #00f2fe",
              borderRadius: 14,
              padding: "24px 20px",
              width: 220,
              textAlign: "center",
              boxShadow: "0 0 25px rgba(0, 242, 254, 0.2)",
            }}
          >
            <div style={{ fontSize: 16, color: "#00f2fe", fontWeight: 700, fontFamily: "monospace" }}>
              STEP 1
            </div>
            <div style={{ fontSize: 26, fontWeight: 700, marginTop: 6 }}>IMU Window</div>
            <div style={{ fontSize: 16, color: "#94a3b8", marginTop: 4 }}>128×6 Stored Data</div>
          </div>

          <div style={{ opacity: step1, color: "#00f2fe", fontSize: 32, fontWeight: 700 }}>➔</div>

          {/* Node 2: Surface AI */}
          <div
            style={{
              opacity: step2,
              backgroundColor: "rgba(15, 23, 42, 0.9)",
              border: "2px solid #3b82f6",
              borderRadius: 14,
              padding: "24px 20px",
              width: 220,
              textAlign: "center",
              boxShadow: "0 0 25px rgba(59, 130, 246, 0.2)",
            }}
          >
            <div style={{ fontSize: 16, color: "#3b82f6", fontWeight: 700, fontFamily: "monospace" }}>
              STEP 2
            </div>
            <div style={{ fontSize: 26, fontWeight: 700, marginTop: 6 }}>Surface AI</div>
            <div style={{ fontSize: 16, color: "#94a3b8", marginTop: 4 }}>RandomForest (9 Class)</div>
          </div>

          <div style={{ opacity: step2, color: "#3b82f6", fontSize: 32, fontWeight: 700 }}>➔</div>

          {/* Node 3: Confidence Gate */}
          <div
            style={{
              opacity: step3,
              backgroundColor: "rgba(15, 23, 42, 0.9)",
              border: "2px solid #ffb703",
              borderRadius: 14,
              padding: "24px 20px",
              width: 240,
              textAlign: "center",
              boxShadow: "0 0 25px rgba(255, 183, 3, 0.2)",
            }}
          >
            <div style={{ fontSize: 16, color: "#ffb703", fontWeight: 700, fontFamily: "monospace" }}>
              STEP 3
            </div>
            <div style={{ fontSize: 26, fontWeight: 700, marginTop: 6 }}>Confidence Gate</div>
            <div style={{ fontSize: 16, color: "#94a3b8", marginTop: 4 }}>Threshold = 0.55</div>
          </div>

          <div style={{ opacity: step3, color: "#ffb703", fontSize: 32, fontWeight: 700 }}>➔</div>

          {/* Node 4: Cargo Policy */}
          <div
            style={{
              opacity: step4,
              backgroundColor: "rgba(15, 23, 42, 0.9)",
              border: "2px solid #8b5cf6",
              borderRadius: 14,
              padding: "24px 20px",
              width: 220,
              textAlign: "center",
              boxShadow: "0 0 25px rgba(139, 92, 246, 0.2)",
            }}
          >
            <div style={{ fontSize: 16, color: "#8b5cf6", fontWeight: 700, fontFamily: "monospace" }}>
              STEP 4
            </div>
            <div style={{ fontSize: 26, fontWeight: 700, marginTop: 6 }}>Cargo Policy</div>
            <div style={{ fontSize: 16, color: "#94a3b8", marginTop: 4 }}>Standard vs Fragile</div>
          </div>

          <div style={{ opacity: step4, color: "#8b5cf6", fontSize: 32, fontWeight: 700 }}>➔</div>

          {/* Node 5: Safety Core */}
          <div
            style={{
              opacity: step5,
              backgroundColor: "rgba(15, 23, 42, 0.95)",
              border: "2px solid #10b981",
              borderRadius: 14,
              padding: "24px 20px",
              width: 260,
              textAlign: "center",
              boxShadow: "0 0 35px rgba(16, 185, 129, 0.3)",
            }}
          >
            <div style={{ fontSize: 16, color: "#10b981", fontWeight: 700, fontFamily: "monospace" }}>
              DECISION CORE
            </div>
            <div style={{ fontSize: 26, fontWeight: 800, color: "#10b981", marginTop: 6 }}>
              Safety Core
            </div>
            <div style={{ fontSize: 16, color: "#e2e8f0", marginTop: 4 }}>
              MOVE / SLOW / HOLD / SAFE_STOP
            </div>
          </div>
        </div>

        {/* Highlight Banner: Non-blocking asynchronous path */}
        <div
          style={{
            opacity: noteOpacity,
            backgroundColor: "rgba(15, 23, 42, 0.95)",
            border: "1px dashed rgba(0, 242, 254, 0.5)",
            borderRadius: 12,
            padding: "18px 40px",
            display: "flex",
            alignItems: "center",
            gap: 20,
            boxShadow: "0 10px 30px rgba(0,0,0,0.5)",
          }}
        >
          <div style={{ fontSize: 32 }}>💡</div>
          <div>
            <div style={{ fontSize: 26, fontWeight: 700, color: "#00f2fe" }}>
              หลักการสำคัญ: ฐานข้อมูลและหน้าเว็บอยู่นอก synchronous safety path
            </div>
            <div style={{ fontSize: 20, color: "#94a3b8", marginTop: 2 }}>
              Safety Core ทำงานบนกฎ deterministic ตัดสินใจได้ต่อเนื่องแม้อยู่ในสภาวะฐานข้อมูลล่ม (Database Outage)
            </div>
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
