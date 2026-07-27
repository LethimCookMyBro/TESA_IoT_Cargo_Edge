import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { HeaderBar } from "../components/HeaderBar";

export const MissionProtectionSceneEn: React.FC = () => {
  const frame = useCurrentFrame();

  const currentPhase =
    frame < 240 ? 1 : frame < 540 ? 2 : frame < 780 ? 3 : 4;

  let activeImage = "assets/current-capture/03_mission_moving.png";
  let statusBadge = "MOVING";
  let statusColor = "#10b981";
  let calloutText = "Select Fragile Cargo ➔ Cautious speed policy applied automatically";

  if (currentPhase === 1) {
    activeImage = "assets/current-capture/02_mission_fragile_cargo.png";
    statusBadge = "FRAGILE CARGO POLICY";
    statusColor = "#3b82f6";
    calloutText = "Fragile Cargo policy enforces stricter speed limits than standard payload";
  } else if (currentPhase === 2) {
    if (frame < 340) {
      activeImage = "assets/current-capture/04_mission_camera_overview.png";
      statusBadge = "OVERVIEW CAMERA";
    } else if (frame < 440) {
      activeImage = "assets/current-capture/05_mission_camera_follow.png";
      statusBadge = "FOLLOW CAMERA";
    } else {
      activeImage = "assets/current-capture/06_mission_camera_robot_pov.png";
      statusBadge = "ROBOT POV CAMERA";
    }
    statusColor = "#00f2fe";
    calloutText = "3D Mission Console: Switch Overview, Follow, and Robot POV cameras in real time";
  } else if (currentPhase === 3) {
    activeImage = "assets/current-capture/07_mission_hold_uncertain.png";
    statusBadge = "HOLD_UNCERTAIN";
    statusColor = "#ffb703";
    calloutText = "AI uncertain? System holds, never guesses (Confidence < 0.55 ➔ HOLD_UNCERTAIN)";
  } else {
    if (frame < 900) {
      activeImage = "assets/current-capture/09_mission_slow_down.png";
      statusBadge = "SLOW_DOWN (50 cm)";
      statusColor = "#ffb703";
      calloutText = "Obstacle detected at 50 cm ➔ Speed ratio reduced (SLOW_DOWN 50%)";
    } else {
      activeImage = "assets/current-capture/10_mission_safe_stopped.png";
      statusBadge = "SAFE_STOPPED (20 cm)";
      statusColor = "#ef233c";
      calloutText = "Safe stop & hold for operator (SAFE_STOP latched until Manual Resume)";
    }
  }

  const overlayOpacity = interpolate(frame % 100, [0, 15], [0.8, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ backgroundColor: "#0b0f19", color: "#ffffff" }}>
      <HeaderBar
        title="CargoShield AI — Mission Protection Console"
        badge={statusBadge}
        badgeColor={statusColor}
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
          border: `2px solid ${statusColor}`,
          boxShadow: `0 20px 60px rgba(0,0,0,0.8), 0 0 30px ${statusColor}44`,
        }}
      >
        <Img
          src={staticFile(activeImage)}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />

        <div
          style={{
            position: "absolute",
            bottom: 30,
            left: 30,
            right: 30,
            backgroundColor: "rgba(11, 15, 25, 0.94)",
            border: `1px solid ${statusColor}`,
            borderRadius: 14,
            padding: "20px 32px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            opacity: overlayOpacity,
            boxShadow: "0 10px 40px rgba(0,0,0,0.8)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
            <div
              style={{
                width: 16,
                height: 16,
                borderRadius: "50%",
                backgroundColor: statusColor,
                boxShadow: `0 0 16px ${statusColor}`,
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
              color: statusColor,
              backgroundColor: `${statusColor}22`,
              padding: "6px 16px",
              borderRadius: 8,
              fontFamily: "monospace",
              letterSpacing: "1px",
            }}
          >
            REAL RUNTIME CAPTURE
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
