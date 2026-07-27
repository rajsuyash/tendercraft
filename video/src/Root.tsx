import React from "react";
import { Composition } from "remotion";

import { Demo } from "./Demo";
import { FPS, SCENES, sec } from "./theme";

export const RemotionRoot: React.FC = () => (
  <Composition
    id="Demo"
    component={Demo}
    durationInFrames={sec(SCENES[SCENES.length - 1]!.to)}
    fps={FPS}
    width={1920}
    height={1080}
  />
);
