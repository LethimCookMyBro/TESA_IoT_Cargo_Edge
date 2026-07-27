import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { HeaderBar } from "../components/HeaderBar";

export const EvidenceSceneEn: React.FC = () => {
  const frame = useCurrentFrame();

  const card1 = interpolate(frame, [10, 25], [0, 1], { extrapolateRight: "clamp" });
  const card2 = interpolate(frame, [30, 45], [0, 1], { extrapolateRight: "clamp" });
  const card3 = interpolate(frame, [50, 65], [0, 1], { extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ backgroundColor: "#0b0f19", color: "#ffffff" }}>
      <HeaderBar title="CargoShield AI — Verification & Empirical Evidence" badge="METRICS & AUDIT" />

      <div
        style={{
          position: "absolute",
          top: 140,
          left: 80,
          right: 80,
          bottom: 120,
          display: "flex",
          flexDirection: "column",
          gap: 32,
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
            System Verification & Model Performance Metrics
          </h2>
          <p style={{ margin: "6px 0 0", fontSize: 22, color: "#94a3b8" }}>
            Empirical evidence read from reports/metrics.json and latest E2E test reports
          </p>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr 1fr",
            gap: 30,
            alignItems: "stretch",
          }}
        >
          <div
            style={{
              opacity: card1,
              backgroundColor: "rgba(15, 23, 42, 0.9)",
              border: "1px solid rgba(0, 242, 254, 0.4)",
              borderRadius: 16,
              padding: "28px 24px",
              boxShadow: "0 10px 30px rgba(0,0,0,0.5)",
              display: "flex",
              flexDirection: "column",
              gap: 16,
            }}
          >
            <div
              style={{
                fontSize: 20,
                fontWeight: 700,
                color: "#00f2fe",
                fontFamily: "monospace",
              }}
            >
              SYSTEM INTEGRATION
            </div>
            <div style={{ fontSize: 48, fontWeight: 800, color: "#ffffff" }}>
              177 <span style={{ fontSize: 24, color: "#10b981" }}>PASSED</span>
            </div>
            <div style={{ fontSize: 20, color: "#94a3b8" }}>
              Automated tests (174 subtests)
              <br />
              compileall & pip-audit clean
            </div>
            <div
              style={{
                marginTop: "auto",
                padding: "12px 16px",
                backgroundColor: "rgba(0, 242, 254, 0.1)",
                borderRadius: 8,
                fontSize: 18,
                color: "#00f2fe",
                fontWeight: 600,
              }}
            >
              MQTT E2E: 14/14 · Fleet Scenario: 12/12
            </div>
          </div>

          <div
            style={{
              opacity: card2,
              backgroundColor: "rgba(15, 23, 42, 0.9)",
              border: "1px solid rgba(255, 183, 3, 0.4)",
              borderRadius: 16,
              padding: "28px 24px",
              boxShadow: "0 10px 30px rgba(0,0,0,0.5)",
              display: "flex",
              flexDirection: "column",
              gap: 16,
            }}
          >
            <div
              style={{
                fontSize: 20,
                fontWeight: 700,
                color: "#ffb703",
                fontFamily: "monospace",
              }}
            >
              SELECTIVE ACCURACY
            </div>
            <div style={{ fontSize: 48, fontWeight: 800, color: "#ffffff" }}>
              72.1% <span style={{ fontSize: 22, color: "#ffb703" }}>(Accepted)</span>
            </div>
            <div style={{ fontSize: 20, color: "#94a3b8" }}>
              Coverage: 52.8% (767/1454)
              <br />
              Confidence Threshold: 0.55
            </div>
            <div
              style={{
                marginTop: "auto",
                padding: "12px 16px",
                backgroundColor: "rgba(255, 183, 3, 0.1)",
                borderRadius: 8,
                fontSize: 18,
                color: "#ffb703",
                fontWeight: 600,
              }}
            >
              687 windows ➔ HOLD_UNCERTAIN
            </div>
          </div>

          <div
            style={{
              opacity: card3,
              backgroundColor: "rgba(15, 23, 42, 0.9)",
              border: "1px solid rgba(139, 92, 246, 0.4)",
              borderRadius: 16,
              padding: "28px 24px",
              boxShadow: "0 10px 30px rgba(0,0,0,0.5)",
              display: "flex",
              flexDirection: "column",
              gap: 16,
            }}
          >
            <div
              style={{
                fontSize: 20,
                fontWeight: 700,
                color: "#8b5cf6",
                fontFamily: "monospace",
              }}
            >
              HELD-OUT TEST SPLIT
            </div>
            <div style={{ fontSize: 36, fontWeight: 800, color: "#ffffff" }}>
              Macro F1: 0.5156
            </div>
            <div style={{ fontSize: 20, color: "#94a3b8" }}>
              Weighted F1: 0.5449
              <br />
              Test Samples: 1,454 (15 groups)
            </div>
            <div
              style={{
                marginTop: "auto",
                padding: "12px 16px",
                backgroundColor: "rgba(139, 92, 246, 0.1)",
                borderRadius: 8,
                fontSize: 18,
                color: "#8b5cf6",
                fontWeight: 600,
              }}
            >
              Group-disjoint held-out dataset
            </div>
          </div>
        </div>

        <div
          style={{
            backgroundColor: "rgba(15, 23, 42, 0.95)",
            border: "1px solid rgba(239, 35, 60, 0.5)",
            borderRadius: 12,
            padding: "16px 32px",
            textAlign: "center",
            boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
          }}
        >
          <span style={{ color: "#ef233c", fontWeight: 700, fontSize: 22, fontFamily: "monospace" }}>
            📌 PROVENANCE NOTE:{" "}
          </span>
          <span style={{ color: "#ffffff", fontSize: 22, fontWeight: 500 }}>
            All timing metrics represent host batch predictions on a workstation simulator, not physical board inference performance.
          </span>
        </div>
      </div>
    </AbsoluteFill>
  );
};
