import React from "react";
import { AbsoluteFill, staticFile } from "remotion";
import { Audio } from "@remotion/media";
import { Series } from "remotion";

import { HookSceneEn } from "./scenes/HookSceneEn";
import { ProblemSceneEn } from "./scenes/ProblemSceneEn";
import { ArchitectureSceneEn } from "./scenes/ArchitectureSceneEn";
import { MissionProtectionSceneEn } from "./scenes/MissionProtectionSceneEn";
import { FleetGuardianSceneEn } from "./scenes/FleetGuardianSceneEn";
import { EvidenceSceneEn } from "./scenes/EvidenceSceneEn";
import { CurrentProposedSceneEn } from "./scenes/CurrentProposedSceneEn";
import { OutroSceneEn } from "./scenes/OutroSceneEn";
import { SubtitleOverlayEn } from "./components/SubtitleOverlayEn";

export const CargoShieldIntroEn: React.FC = () => {
  return (
    <AbsoluteFill style={{ backgroundColor: "#0b0f19" }}>
      {/* English Voiceover Audio Track */}
      <Audio src={staticFile("assets/audio/voiceover_en.mp3")} volume={1.0} />

      {/* Main 120-Second Series Timeline */}
      <Series>
        {/* Scene 1: Hook (0s - 6s: 180 frames) */}
        <Series.Sequence durationInFrames={180}>
          <HookSceneEn />
        </Series.Sequence>

        {/* Scene 2: Problem (6s - 20s: 420 frames) */}
        <Series.Sequence durationInFrames={420}>
          <ProblemSceneEn />
        </Series.Sequence>

        {/* Scene 3: Architecture & Pipeline (20s - 38s: 540 frames) */}
        <Series.Sequence durationInFrames={540}>
          <ArchitectureSceneEn />
        </Series.Sequence>

        {/* Scene 4: Mission Protection Walkthrough (38s - 72s: 1020 frames) */}
        <Series.Sequence durationInFrames={1020}>
          <MissionProtectionSceneEn />
        </Series.Sequence>

        {/* Scene 5: Fleet Guardian & Maintenance (72s - 94s: 660 frames) */}
        <Series.Sequence durationInFrames={660}>
          <FleetGuardianSceneEn />
        </Series.Sequence>

        {/* Scene 6: Verification Metrics (94s - 108s: 420 frames) */}
        <Series.Sequence durationInFrames={420}>
          <EvidenceSceneEn />
        </Series.Sequence>

        {/* Scene 7: CURRENT vs PROPOSED Scope (108s - 116s: 240 frames) */}
        <Series.Sequence durationInFrames={240}>
          <CurrentProposedSceneEn />
        </Series.Sequence>

        {/* Scene 8: Outro & Logo (116s - 120s: 120 frames) */}
        <Series.Sequence durationInFrames={120}>
          <OutroSceneEn />
        </Series.Sequence>
      </Series>

      {/* Burn-in English Subtitles Overlay */}
      <SubtitleOverlayEn />
    </AbsoluteFill>
  );
};
