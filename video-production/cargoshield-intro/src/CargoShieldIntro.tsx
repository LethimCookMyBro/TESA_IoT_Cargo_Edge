import React from "react";
import { AbsoluteFill, staticFile } from "remotion";
import { Audio } from "@remotion/media";
import { Series } from "remotion";

import { HookScene } from "./scenes/HookScene";
import { ProblemScene } from "./scenes/ProblemScene";
import { ArchitectureScene } from "./scenes/ArchitectureScene";
import { MissionProtectionScene } from "./scenes/MissionProtectionScene";
import { FleetGuardianScene } from "./scenes/FleetGuardianScene";
import { EvidenceScene } from "./scenes/EvidenceScene";
import { CurrentProposedScene } from "./scenes/CurrentProposedScene";
import { OutroScene } from "./scenes/OutroScene";
import { SubtitleOverlay } from "./components/SubtitleOverlay";

export const CargoShieldIntro: React.FC = () => {
  return (
    <AbsoluteFill style={{ backgroundColor: "#0b0f19" }}>
      {/* Thai Voiceover Audio Track */}
      <Audio src={staticFile("assets/audio/voiceover_th.mp3")} volume={1.0} />

      {/* Main 120-Second Series Timeline */}
      <Series>
        {/* Scene 1: Hook (0s - 6s: 180 frames) */}
        <Series.Sequence durationInFrames={180}>
          <HookScene />
        </Series.Sequence>

        {/* Scene 2: Problem (6s - 20s: 420 frames) */}
        <Series.Sequence durationInFrames={420}>
          <ProblemScene />
        </Series.Sequence>

        {/* Scene 3: Architecture & Pipeline (20s - 38s: 540 frames) */}
        <Series.Sequence durationInFrames={540}>
          <ArchitectureScene />
        </Series.Sequence>

        {/* Scene 4: Mission Protection Walkthrough (38s - 72s: 1020 frames) */}
        <Series.Sequence durationInFrames={1020}>
          <MissionProtectionScene />
        </Series.Sequence>

        {/* Scene 5: Fleet Guardian & Maintenance (72s - 94s: 660 frames) */}
        <Series.Sequence durationInFrames={660}>
          <FleetGuardianScene />
        </Series.Sequence>

        {/* Scene 6: Verification Metrics (94s - 108s: 420 frames) */}
        <Series.Sequence durationInFrames={420}>
          <EvidenceScene />
        </Series.Sequence>

        {/* Scene 7: CURRENT vs PROPOSED Scope (108s - 116s: 240 frames) */}
        <Series.Sequence durationInFrames={240}>
          <CurrentProposedScene />
        </Series.Sequence>

        {/* Scene 8: Outro & Logo (116s - 120s: 120 frames) */}
        <Series.Sequence durationInFrames={120}>
          <OutroScene />
        </Series.Sequence>
      </Series>

      {/* Burn-in Subtitles Overlay */}
      <SubtitleOverlay />
    </AbsoluteFill>
  );
};
