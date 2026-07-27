import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { HeaderBar } from "../components/HeaderBar";

export const ProblemSceneEn: React.FC = () => {
  const frame = useCurrentFrame();

  const card1Opacity = interpolate(frame, [15, 35], [0, 1], { extrapolateRight: "clamp" });
  const card2Opacity = interpolate(frame, [45, 65], [0, 1], { extrapolateRight: "clamp" });
  const card3Opacity = interpolate(frame, [75, 95], [0, 1], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ backgroundColor: "#0b0f19", color: "#ffffff" }}>
      <HeaderBar title="CargoShield AI — Problem Definition" badge="THE UNSEEN RISK" />

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
              Robots only know "destination target", blind to "in-transit cargo vibration risk"
            </div>
          </div>
        </div>

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
            <h3 style={{ margin: 0, fontSize: 30, color: "#ffffff", fontWeight: 700 }}>
              1. Floor Surfaces Cause Different Vibration Risks
            </h3>
            <p style={{ margin: "8px 0 0", fontSize: 22, color: "#94a3b8", lineHeight: 1.4 }}>
              The shortest path may cross rough tiles or concrete joints, exposing goods to high acceleration peaks.
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
            <h3 style={{ margin: 0, fontSize: 30, color: "#ffffff", fontWeight: 700 }}>
              2. Fragile Cargo Requires Tailored Policy
            </h3>
            <p style={{ margin: "8px 0 0", fontSize: 22, color: "#94a3b8", lineHeight: 1.4 }}>
              Standard items and delicate payloads should never be driven under identical speed limits or risk thresholds.
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
            <h3 style={{ margin: 0, fontSize: 30, color: "#ffffff", fontWeight: 700 }}>
              3. CargoShield AI Bridges The Gap
            </h3>
            <p style={{ margin: "8px 0 0", fontSize: 22, color: "#94a3b8", lineHeight: 1.4 }}>
              Operates as a dedicated Cargo Protection Layer between sensor telemetry and robot motion commands.
            </p>
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
