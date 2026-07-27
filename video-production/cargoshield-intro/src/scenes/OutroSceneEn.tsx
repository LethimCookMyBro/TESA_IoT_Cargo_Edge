import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";

export const OutroSceneEn: React.FC = () => {
  const frame = useCurrentFrame();

  const logoScale = interpolate(frame, [0, 45], [0.85, 1.0], {
    extrapolateRight: "clamp",
  });

  const contentOpacity = interpolate(frame, [0, 30], [0, 1], {
    extrapolateRight: "clamp",
  });

  const pulse = interpolate(frame % 60, [0, 30, 60], [1, 1.08, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#0b0f19",
        color: "#ffffff",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        textAlign: "center",
        padding: "0 120px",
      }}
    >
      <div
        style={{
          position: "absolute",
          width: 800,
          height: 800,
          borderRadius: "50%",
          background:
            "radial-gradient(circle, rgba(0, 242, 254, 0.15) 0%, rgba(11, 15, 25, 0) 70%)",
          transform: `scale(${pulse})`,
        }}
      />

      <div
        style={{
          opacity: contentOpacity,
          transform: `scale(${logoScale})`,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 24,
          zIndex: 10,
        }}
      >
        <div
          style={{
            padding: "8px 24px",
            borderRadius: 30,
            backgroundColor: "rgba(0, 242, 254, 0.15)",
            border: "1px solid rgba(0, 242, 254, 0.4)",
            color: "#00f2fe",
            fontSize: 20,
            fontWeight: 700,
            letterSpacing: "3px",
            textTransform: "uppercase",
            fontFamily: "monospace",
          }}
        >
          CargoShield AI
        </div>

        <h1
          style={{
            margin: 0,
            fontSize: 84,
            fontWeight: 800,
            letterSpacing: "-1px",
            background: "linear-gradient(90deg, #ffffff 0%, #00f2fe 100%)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            textShadow: "0 0 50px rgba(0, 242, 254, 0.5)",
            fontFamily: "Inter, Roboto, sans-serif",
          }}
        >
          CargoShield AI
        </h1>

        <div
          style={{
            fontSize: 48,
            fontWeight: 700,
            color: "#ffffff",
            fontStyle: "italic",
            letterSpacing: "0.5px",
            fontFamily: "Inter, Roboto, sans-serif",
          }}
        >
          “Protect the cargo. Explain every decision.”
        </div>

        <div
          style={{
            fontSize: 24,
            color: "#94a3b8",
            marginTop: 16,
            fontWeight: 500,
            letterSpacing: "1px",
            fontFamily: "monospace",
          }}
        >
          SOFTWARE PROTOTYPE · DATASET REPLAY · WORKSTATION EVIDENCE
        </div>
      </div>
    </AbsoluteFill>
  );
};
