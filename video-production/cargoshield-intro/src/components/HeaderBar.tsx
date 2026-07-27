import React from "react";
import { interpolate, useCurrentFrame } from "remotion";

export const HeaderBar: React.FC<{
  title?: string;
  badge?: string;
  badgeColor?: string;
}> = ({
  title = "CargoShield AI — Cargo-Aware Autonomy",
  badge = "SOFTWARE PROTOTYPE · DATASET REPLAY",
  badgeColor = "#00f2fe",
}) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 15], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        position: "absolute",
        top: 40,
        left: 80,
        right: 80,
        height: 70,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        borderBottom: "1px solid rgba(0, 242, 254, 0.2)",
        paddingBottom: 15,
        opacity,
        zIndex: 50,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <div
          style={{
            width: 14,
            height: 14,
            borderRadius: "50%",
            backgroundColor: badgeColor,
            boxShadow: `0 0 12px ${badgeColor}`,
          }}
        />
        <span
          style={{
            color: "#ffffff",
            fontSize: 28,
            fontWeight: 700,
            letterSpacing: "0.5px",
            fontFamily: "Sarabun, sans-serif",
          }}
        >
          {title}
        </span>
      </div>

      <div
        style={{
          backgroundColor: "rgba(11, 15, 25, 0.85)",
          border: `1px solid ${badgeColor}`,
          borderRadius: 8,
          padding: "6px 18px",
          color: badgeColor,
          fontSize: 18,
          fontWeight: 600,
          letterSpacing: "1px",
          fontFamily: "monospace",
          boxShadow: `0 0 15px rgba(0, 242, 254, 0.15)`,
        }}
      >
        {badge}
      </div>
    </div>
  );
};
