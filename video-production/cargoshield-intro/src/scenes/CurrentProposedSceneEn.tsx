import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { HeaderBar } from "../components/HeaderBar";

export const CurrentProposedSceneEn: React.FC = () => {
  const frame = useCurrentFrame();

  const currentOpacity = interpolate(frame, [10, 30], [0, 1], { extrapolateRight: "clamp" });
  const proposedOpacity = interpolate(frame, [35, 55], [0, 1], { extrapolateRight: "clamp" });
  const bannerOpacity = interpolate(frame, [60, 80], [0, 1], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ backgroundColor: "#0b0f19", color: "#ffffff" }}>
      <HeaderBar title="CargoShield AI — Project Scope Matrix" badge="CURRENT vs PROPOSED" />

      <div
        style={{
          position: "absolute",
          top: 140,
          left: 80,
          right: 80,
          bottom: 120,
          display: "flex",
          flexDirection: "column",
          gap: 30,
        }}
      >
        <div style={{ textAlign: "center" }}>
          <h2
            style={{
              margin: 0,
              fontSize: 44,
              fontWeight: 800,
              color: "#ffffff",
              fontFamily: "Inter, Roboto, sans-serif",
            }}
          >
            Current Delivered Scope vs Proposed Hardware Design
          </h2>
          <p style={{ margin: "6px 0 0", fontSize: 22, color: "#94a3b8" }}>
            Transparent distinction between verified working prototype features and future designs
          </p>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 40,
            flex: 1,
          }}
        >
          <div
            style={{
              opacity: currentOpacity,
              backgroundColor: "rgba(16, 185, 129, 0.08)",
              border: "2px solid #10b981",
              borderRadius: 16,
              padding: "32px",
              display: "flex",
              flexDirection: "column",
              gap: 20,
              boxShadow: "0 10px 40px rgba(16, 185, 129, 0.15)",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                borderBottom: "1px solid rgba(16, 185, 129, 0.3)",
                paddingBottom: 16,
              }}
            >
              <h3 style={{ margin: 0, fontSize: 34, fontWeight: 800, color: "#10b981" }}>
                CURRENT
              </h3>
              <span
                style={{
                  backgroundColor: "#10b981",
                  color: "#0b0f19",
                  fontSize: 16,
                  fontWeight: 800,
                  padding: "4px 14px",
                  borderRadius: 6,
                  fontFamily: "monospace",
                }}
              >
                WORKING PROTOTYPE
              </span>
            </div>

            <ul
              style={{
                margin: 0,
                paddingLeft: 24,
                display: "flex",
                flexDirection: "column",
                gap: 16,
                fontSize: 22,
                color: "#e2e8f0",
                lineHeight: 1.4,
              }}
            >
              <li>
                <strong>Dataset Replay:</strong> Replays stored 128×6 IMU windows into pipeline
              </li>
              <li>
                <strong>Software Safety Core:</strong> Deterministic MOVE / SLOW / HOLD / SAFE_STOP rules
              </li>
              <li>
                <strong>3D Mission Console:</strong> Web-based Three.js visualization console
              </li>
              <li>
                <strong>Fleet Guardian:</strong> Postgres Historian & Multi-robot status tracking
              </li>
              <li>
                <strong>Maintenance Copilot:</strong> Deterministic read-only allowlisted queries
              </li>
            </ul>
          </div>

          <div
            style={{
              opacity: proposedOpacity,
              backgroundColor: "rgba(0, 242, 254, 0.08)",
              border: "2px dashed #00f2fe",
              borderRadius: 16,
              padding: "32px",
              display: "flex",
              flexDirection: "column",
              gap: 20,
              boxShadow: "0 10px 40px rgba(0, 242, 254, 0.15)",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                borderBottom: "1px solid rgba(0, 242, 254, 0.3)",
                paddingBottom: 16,
              }}
            >
              <h3 style={{ margin: 0, fontSize: 34, fontWeight: 800, color: "#00f2fe" }}>
                PROPOSED
              </h3>
              <span
                style={{
                  backgroundColor: "rgba(0, 242, 254, 0.2)",
                  color: "#00f2fe",
                  border: "1px solid #00f2fe",
                  fontSize: 16,
                  fontWeight: 800,
                  padding: "4px 14px",
                  borderRadius: 6,
                  fontFamily: "monospace",
                }}
              >
                FUTURE ARCHITECTURE
              </span>
            </div>

            <ul
              style={{
                margin: 0,
                paddingLeft: 24,
                display: "flex",
                flexDirection: "column",
                gap: 16,
                fontSize: 22,
                color: "#cbd5e1",
                lineHeight: 1.4,
              }}
            >
              <li>
                <strong>Live BMI270 Sensor:</strong> Direct hardware telemetry sampling
              </li>
              <li>
                <strong>On-Board Inference:</strong> Edge ML execution on physical MCU/SoC
              </li>
              <li>
                <strong>mTLS Security:</strong> Mutual TLS authentication between robot and cloud
              </li>
              <li>
                <strong>OPTIGA / SoC Secure Enclave:</strong> Hardware key storage and attestation
              </li>
              <li>
                <strong>Secure Boot & Protected Update:</strong> Tamper-resistant firmware updates
              </li>
            </ul>
          </div>
        </div>

        <div
          style={{
            opacity: bannerOpacity,
            backgroundColor: "rgba(15, 23, 42, 0.95)",
            border: "1px solid #ffb703",
            borderRadius: 12,
            padding: "16px 32px",
            textAlign: "center",
            boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
          }}
        >
          <span style={{ color: "#ffb703", fontWeight: 700, fontSize: 24, fontFamily: "monospace" }}>
            🔒 SECURE EDGE STATUS:{" "}
          </span>
          <span style={{ color: "#ffffff", fontSize: 24, fontWeight: 600 }}>
            Architectural design complete; currently pending physical hardware deployment.
          </span>
        </div>
      </div>
    </AbsoluteFill>
  );
};
