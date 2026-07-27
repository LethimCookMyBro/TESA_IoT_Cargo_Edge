import React from "react";
import { AbsoluteFill, Img, interpolate, staticFile, useCurrentFrame } from "remotion";
import { HeaderBar } from "../components/HeaderBar";

export const HookSceneEn: React.FC = () => {
  const frame = useCurrentFrame();

  const logoScale = interpolate(frame, [0, 60], [0.85, 1.0], {
    extrapolateRight: "clamp",
  });

  const titleOpacity = interpolate(frame, [15, 45], [0, 1], {
    extrapolateRight: "clamp",
  });

  const subtitleOpacity = interpolate(frame, [35, 65], [0, 1], {
    extrapolateRight: "clamp",
  });

  const bgZoom = interpolate(frame, [0, 180], [1.0, 1.05], {
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ backgroundColor: "#0b0f19", overflow: "hidden" }}>
      <div
        style={{
          position: "absolute",
          inset: 0,
          opacity: 0.35,
          scale: bgZoom,
          filter: "blur(4px)",
        }}
      >
        <Img
          src={staticFile("assets/current-capture/01_mission_idle.png")}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
        />
      </div>

      <div
        style={{
          position: "absolute",
          inset: 0,
          backgroundImage:
            "radial-gradient(circle at 50% 50%, rgba(0, 242, 254, 0.12) 0%, rgba(11, 15, 25, 0.95) 75%)",
        }}
      />

      <HeaderBar title="CargoShield AI" badge="SOFTWARE PROTOTYPE · DATASET REPLAY" />

      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap: 24,
          padding: "0 120px",
          textAlign: "center",
          zIndex: 10,
        }}
      >
        <div
          style={{
            scale: logoScale,
            opacity: titleOpacity,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 16,
          }}
        >
          <div
            style={{
              padding: "8px 24px",
              borderRadius: 30,
              backgroundColor: "rgba(0, 242, 254, 0.15)",
              border: "1px solid rgba(0, 242, 254, 0.4)",
              color: "#00f2fe",
              fontSize: 22,
              fontWeight: 700,
              letterSpacing: "3px",
              textTransform: "uppercase",
              fontFamily: "monospace",
            }}
          >
            Cargo Protection Layer
          </div>

          <h1
            style={{
              margin: 0,
              fontSize: 74,
              fontWeight: 800,
              color: "#ffffff",
              letterSpacing: "-1px",
              lineHeight: 1.15,
              textShadow: "0 0 40px rgba(0, 242, 254, 0.4)",
              fontFamily: "Inter, Roboto, sans-serif",
            }}
          >
            From Unseen Transit Risks
            <br />
            <span
              style={{
                background: "linear-gradient(90deg, #00f2fe 0%, #4facfe 100%)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
              }}
            >
              To Cargo-Aware Autonomy
            </span>
          </h1>
        </div>

        <p
          style={{
            margin: 0,
            opacity: subtitleOpacity,
            fontSize: 32,
            color: "#94a3b8",
            maxWidth: 1000,
            fontWeight: 500,
            lineHeight: 1.5,
            fontFamily: "Inter, Roboto, sans-serif",
          }}
        >
          Vibration risk analysis, adaptive speed policy, route re-planning,
          and fail-safe stops for cargo transport robots.
        </p>
      </div>
    </AbsoluteFill>
  );
};
