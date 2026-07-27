import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { HeaderBar } from "../components/HeaderBar";

export const FleetGuardianSceneEn: React.FC = () => {
  const frame = useCurrentFrame();

  let activeImage = "assets/current-capture/11_fleet_overview.png";
  let statusBadge = "FLEET OVERVIEW";
  let badgeColor = "#00f2fe";
  let calloutText = "Multi-robot fleet tracking & per-robot safety isolation";

  if (frame >= 220 && frame < 440) {
    activeImage = "assets/current-capture/12_fleet_safety_events_p1.png";
    statusBadge = "SAFETY EVENTS HISTORIAN";
    badgeColor = "#3b82f6";
    calloutText = "Non-blocking PostgreSQL logging for Safety Events and Mission History";
  } else if (frame >= 440) {
    activeImage = "assets/current-capture/16_fleet_maintenance_assistant.png";
    statusBadge = "MAINTENANCE ASSISTANT";
    badgeColor = "#ffb703";
    calloutText = "Maintenance Assistant: Deterministic · Read-Only · Human Approval Required";
  }

  const badgeOpacity = interpolate(frame % 80, [0, 15], [0.85, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ backgroundColor: "#0b0f19", color: "#ffffff" }}>
      <HeaderBar
        title="Fleet Guardian — Multi-Robot Intelligence"
        badge={statusBadge}
        badgeColor={badgeColor}
      />

      <div
        style={{
          position: "absolute",
          top: 130,
          left: 80,
          right: 80,
          bottom: 130,
          borderRadius: 16,
          overflow: "hidden",
          border: `2px solid ${badgeColor}`,
          boxShadow: `0 20px 60px rgba(0,0,0,0.8), 0 0 30px ${badgeColor}44`,
        }}
      >
        <Img
          src={staticFile(activeImage)}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />

        {frame >= 440 && (
          <div
            style={{
              position: "absolute",
              top: 24,
              right: 24,
              display: "flex",
              gap: 12,
              opacity: badgeOpacity,
            }}
          >
            <div
              style={{
                backgroundColor: "rgba(11, 15, 25, 0.95)",
                border: "1px solid #10b981",
                color: "#10b981",
                padding: "8px 16px",
                borderRadius: 8,
                fontSize: 16,
                fontWeight: 700,
                fontFamily: "monospace",
              }}
            >
              READ-ONLY
            </div>
            <div
              style={{
                backgroundColor: "rgba(11, 15, 25, 0.95)",
                border: "1px solid #ffb703",
                color: "#ffb703",
                padding: "8px 16px",
                borderRadius: 8,
                fontSize: 16,
                fontWeight: 700,
                fontFamily: "monospace",
              }}
            >
              HUMAN APPROVAL REQUIRED
            </div>
            <div
              style={{
                backgroundColor: "rgba(11, 15, 25, 0.95)",
                border: "1px solid #ef233c",
                color: "#ef233c",
                padding: "8px 16px",
                borderRadius: 8,
                fontSize: 16,
                fontWeight: 700,
                fontFamily: "monospace",
              }}
            >
              Hermes provider: Not connected
            </div>
          </div>
        )}

        <div
          style={{
            position: "absolute",
            bottom: 30,
            left: 30,
            right: 30,
            backgroundColor: "rgba(11, 15, 25, 0.94)",
            border: `1px solid ${badgeColor}`,
            borderRadius: 14,
            padding: "20px 32px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            boxShadow: "0 10px 40px rgba(0,0,0,0.8)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
            <div
              style={{
                width: 16,
                height: 16,
                borderRadius: "50%",
                backgroundColor: badgeColor,
                boxShadow: `0 0 16px ${badgeColor}`,
              }}
            />
            <div
              style={{
                fontSize: 26,
                fontWeight: 700,
                color: "#ffffff",
                fontFamily: "Inter, Roboto, sans-serif",
              }}
            >
              {calloutText}
            </div>
          </div>

          <div
            style={{
              fontSize: 18,
              fontWeight: 700,
              color: badgeColor,
              backgroundColor: `${badgeColor}22`,
              padding: "6px 16px",
              borderRadius: 8,
              fontFamily: "monospace",
              letterSpacing: "1px",
            }}
          >
            FLEET GUARDIAN MODULE
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
