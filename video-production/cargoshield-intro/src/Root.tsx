import React from "react";
import { Composition } from "remotion";
import { CargoShieldIntro } from "./CargoShieldIntro";
import { CargoShieldIntroEn } from "./CargoShieldIntroEn";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="CargoShieldIntro2Min"
        component={CargoShieldIntro}
        durationInFrames={3600}
        fps={30}
        width={1920}
        height={1080}
      />
      <Composition
        id="CargoShieldIntro2MinEn"
        component={CargoShieldIntroEn}
        durationInFrames={3600}
        fps={30}
        width={1920}
        height={1080}
      />
    </>
  );
};
