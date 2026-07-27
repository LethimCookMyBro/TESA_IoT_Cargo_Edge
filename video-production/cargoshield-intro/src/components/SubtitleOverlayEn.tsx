import React from "react";
import { interpolate, useCurrentFrame } from "remotion";

export interface SubtitleItem {
  id: number;
  startFrame: number;
  endFrame: number;
  text: string;
}

export const SUBTITLES_EN: SubtitleItem[] = [
  {
    id: 1,
    startFrame: 15,
    endFrame: 174,
    text: "From unseen transit risks to Cargo-Aware Autonomy:\nIntroducing CargoShield AI for cargo transport robots.",
  },
  {
    id: 2,
    startFrame: 186,
    endFrame: 375,
    text: "Reaching the destination does not mean\nthe cargo was protected along the way.",
  },
  {
    id: 3,
    startFrame: 384,
    endFrame: 585,
    text: "Floor vibrations and varying surfaces pose high risks to fragile items.\nCargoShield AI adds a dedicated decision layer for cargo risk assessment.",
  },
  {
    id: 4,
    startFrame: 606,
    endFrame: 855,
    text: "The system feeds IMU windows into Surface AI for classification,\npasses a Confidence Gate, evaluates Vibration Risk, and executes Cargo Policy.",
  },
  {
    id: 5,
    startFrame: 864,
    endFrame: 1125,
    text: "The Safety Core acts as the sole deterministic decision maker.\nThe database sits safely outside the synchronous safety path.",
  },
  {
    id: 6,
    startFrame: 1146,
    endFrame: 1395,
    text: "In the Mission Protection Console, selecting fragile cargo\nautomatically applies a cautious speed policy.",
  },
  {
    id: 7,
    startFrame: 1404,
    endFrame: 1665,
    text: "If the AI model lacks confidence in classification,\nthe system immediately enters HOLD UNCERTAIN to avoid guessing.",
  },
  {
    id: 8,
    startFrame: 1674,
    endFrame: 1995,
    text: "When obstacles or hazards are detected, it triggers a latched SAFE STOP\nuntil manually resumed by an operator.",
  },
  {
    id: 9,
    startFrame: 2010,
    endFrame: 2244,
    text: "Camera viewports support Overview, Follow, and Robot POV\nfor real-time mission monitoring.",
  },
  {
    id: 10,
    startFrame: 2256,
    endFrame: 2505,
    text: "For fleet operators, Fleet Guardian provides multi-robot status monitoring,\nSafety Event logging, and mission history tracking.",
  },
  {
    id: 11,
    startFrame: 2514,
    endFrame: 2805,
    text: "Featuring a deterministic, read-only Maintenance Assistant (human approval required),\nwith Hermes provider not connected.",
  },
  {
    id: 12,
    startFrame: 2826,
    endFrame: 3045,
    text: "CargoShield is verified by 177 automated tests,\n14/14 MQTT end-to-end checks, and 12/12 fleet scenario tests.",
  },
  {
    id: 13,
    startFrame: 3054,
    endFrame: 3225,
    text: "On a held-out dataset, the model achieves 72.1% selective accuracy,\nprioritizing safe stops over low confidence predictions.",
  },
  {
    id: 14,
    startFrame: 3246,
    endFrame: 3465,
    text: "Currently, CargoShield operates as a Software Prototype using Dataset Replay.\nLive BMI270, mTLS, OPTIGA Enclave, and Secure Boot represent our proposed design.",
  },
  {
    id: 15,
    startFrame: 3480,
    endFrame: 3594,
    text: "CargoShield AI\nProtect the cargo. Explain every decision.",
  },
];

export const SubtitleOverlayEn: React.FC = () => {
  const frame = useCurrentFrame();

  const activeSubtitle = SUBTITLES_EN.find(
    (sub) => frame >= sub.startFrame && frame <= sub.endFrame
  );

  if (!activeSubtitle) return null;

  const fadeIn = interpolate(
    frame,
    [activeSubtitle.startFrame, activeSubtitle.startFrame + 8],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const fadeOut = interpolate(
    frame,
    [activeSubtitle.endFrame - 8, activeSubtitle.endFrame],
    [1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
  );

  const opacity = Math.min(fadeIn, fadeOut);

  return (
    <div
      style={{
        position: "absolute",
        bottom: 50,
        left: 100,
        right: 100,
        display: "flex",
        justifyContent: "center",
        pointerEvents: "none",
        zIndex: 100,
        opacity,
      }}
    >
      <div
        style={{
          backgroundColor: "rgba(11, 15, 25, 0.92)",
          border: "1px solid rgba(0, 242, 254, 0.4)",
          boxShadow: "0 8px 32px rgba(0, 0, 0, 0.6)",
          borderRadius: 12,
          padding: "14px 32px",
          maxWidth: "85%",
          textAlign: "center",
        }}
      >
        <span
          style={{
            color: "#ffffff",
            fontSize: 30,
            lineHeight: 1.4,
            fontWeight: 600,
            whiteSpace: "pre-line",
            textShadow: "0 2px 4px rgba(0,0,0,0.8)",
            fontFamily: "Inter, Roboto, sans-serif",
          }}
        >
          {activeSubtitle.text}
        </span>
      </div>
    </div>
  );
};
