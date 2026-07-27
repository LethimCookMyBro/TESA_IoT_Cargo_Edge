# CargoShield AI Intro Video Project (Remotion)

This directory contains the Remotion project for rendering the 2-minute introductory video for CargoShield AI.

## Project Structure

```text
video-production/cargoshield-intro/
├── package.json
├── remotion.config.ts
├── tsconfig.json
├── src/
│   ├── index.ts
│   ├── Root.tsx
│   ├── CargoShieldIntro.tsx
│   ├── components/
│   │   ├── HeaderBar.tsx
│   │   └── SubtitleOverlay.tsx
│   └── scenes/
│       ├── HookScene.tsx
│       ├── ProblemScene.tsx
│       ├── ArchitectureScene.tsx
│       ├── MissionProtectionScene.tsx
│       ├── FleetGuardianScene.tsx
│       ├── EvidenceScene.tsx
│       ├── CurrentProposedScene.tsx
│       └── OutroScene.tsx
├── public/
│   └── assets/
│       ├── audio/
│       │   └── voiceover_th.mp3
│       └── current-capture/
│           ├── 01_mission_idle.png
│           ├── ...
│           └── capture_manifest.json
├── capture_manifest.json
├── STORYBOARD.md
├── voiceover_th.txt
├── captions_th.srt
├── ASSET_LICENSES.md
└── README.md
```

## Render Instructions

### 1. Preview in Remotion Studio

```bash
npx remotion studio
```

### 2. Render Representative Still Frame

```bash
npx remotion still CargoShieldIntro2Min --frame=30
```

### 3. Render Final MP4 Video

```bash
npx remotion render CargoShieldIntro2Min ../../reports/media/cargoshield_program_intro_2min.mp4
```

Output specs:
- **Format**: MP4 (H.264 / AAC)
- **Resolution**: 1920×1080
- **Frame Rate**: 30 fps
- **Duration**: 120.0 seconds (3600 frames)
- **Pixel Format**: `yuv420p`
- **FastStart**: Enabled
