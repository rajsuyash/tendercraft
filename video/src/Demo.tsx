import React from "react";
import { AbsoluteFill, Audio, Sequence, staticFile } from "remotion";

import { Cite, Close, Denominator, Extract, Matrix, Problem } from "./scenes";
import { SCENES, dur, sec } from "./theme";

const COMPONENTS = [Problem, Extract, Denominator, Matrix, Cite, Close];

/**
 * The film.
 *
 * Scene boundaries come from ffmpeg silencedetect run over the real voiceover, not from
 * guesses, so every cut lands in a pause between paragraphs instead of over a word. The audio
 * is one continuous track: cutting narration per scene is how you get clipped consonants.
 */
export const Demo: React.FC = () => (
  <AbsoluteFill style={{ backgroundColor: "#faf8ff" }}>
    <Audio src={staticFile("voiceover.mp3")} />
    {SCENES.map((s, i) => {
      const Scene = COMPONENTS[i]!;
      return (
        <Sequence key={s.id} from={sec(s.from)} durationInFrames={dur(i)} name={s.id}>
          <Scene />
        </Sequence>
      );
    })}
  </AbsoluteFill>
);
