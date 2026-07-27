import React from "react";
import { AbsoluteFill, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";

import { T } from "./theme";

/** Ease-out entrance shared by every scene, so the film has one motion signature. */
const useEnter = (delay = 0) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({ frame: frame - delay, fps, config: { damping: 200, mass: 0.6 }, durationInFrames: 22 });
};

const Line: React.FC<{ children: React.ReactNode; delay?: number; size?: number; color?: string; weight?: number }> = ({
  children, delay = 0, size = 64, color = T.ink, weight = 700,
}) => {
  const e = useEnter(delay);
  return (
    <div
      style={{
        fontFamily: T.display, fontSize: size, fontWeight: weight, color,
        letterSpacing: "-0.03em", lineHeight: 1.1,
        opacity: e, transform: `translateY(${interpolate(e, [0, 1], [18, 0])}px)`,
      }}
    >
      {children}
    </div>
  );
};

/** Scene 1 — the document nobody can read in full. */
export const Problem: React.FC = () => {
  const frame = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: T.bg, padding: 120, justifyContent: "center" }}>
      {/* 300 stacked rules standing in for 300 pages: the scale is the point, not the detail. */}
      <AbsoluteFill style={{ alignItems: "flex-end", justifyContent: "center", paddingRight: 90 }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 3, width: 520, opacity: 0.5 }}>
          {Array.from({ length: 46 }).map((_, i) => {
            const on = interpolate(frame, [10 + i * 2, 26 + i * 2], [0, 1], { extrapolateRight: "clamp", extrapolateLeft: "clamp" });
            return (
              <div key={i} style={{ height: 6, borderRadius: 3, background: i % 7 === 3 ? T.accent : T.primary,
                opacity: on * (i % 7 === 3 ? 0.9 : 0.22), transform: `scaleX(${on})`, transformOrigin: "left" }} />
            );
          })}
        </div>
      </AbsoluteFill>

      <div style={{ position: "relative", maxWidth: 900 }}>
        <Line size={72}>A government tender</Line>
        <Line size={72} delay={6}>runs 300 pages.</Line>
        <div style={{ marginTop: 34 }}>
          <Line size={30} delay={40} weight={400} color={T.inkSoft}>
            The requirements that decide whether your bid is read
          </Line>
          <Line size={30} delay={46} weight={400} color={T.inkSoft}>
            are somewhere inside it.
          </Line>
        </div>
      </div>
    </AbsoluteFill>
  );
};

/** Scene 2 — extraction. A counter that lands on the real figure from a real run. */
export const Extract: React.FC = () => {
  const frame = useCurrentFrame();
  const count = Math.round(interpolate(frame, [40, 150], [0, 192], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));
  const pages = Math.round(interpolate(frame, [24, 96], [0, 81], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));

  return (
    <AbsoluteFill style={{ background: T.bg, padding: 120, justifyContent: "center" }}>
      <Line size={30} weight={500} color={T.primary}>NABARD · NAFIS Third Round</Line>
      <div style={{ height: 26 }} />
      <div style={{ display: "flex", gap: 90, alignItems: "flex-end" }}>
        <div>
          <div style={{ fontFamily: T.display, fontSize: 150, fontWeight: 800, color: T.ink, letterSpacing: "-0.04em", lineHeight: 1 }}>
            {pages}
          </div>
          <Line size={26} delay={30} weight={400} color={T.inkSoft}>pages read</Line>
        </div>
        <div>
          <div style={{ fontFamily: T.display, fontSize: 150, fontWeight: 800, color: T.primary, letterSpacing: "-0.04em", lineHeight: 1 }}>
            {count}
          </div>
          <Line size={26} delay={60} weight={400} color={T.inkSoft}>requirements extracted</Line>
        </div>
      </div>

      {/* Anchors appearing one by one: the claim is not "we found things", it is "we can show
          you exactly where each one came from". */}
      <div style={{ marginTop: 64, display: "flex", flexDirection: "column", gap: 12 }}>
        {[
          ["p.8 · Cl. 3.1(a)", "Average annual turnover of not less than Rs. 5 Crore"],
          ["p.12 · Cl. 4.2", "Valid ISO 9001:2015 certificate on the date of submission"],
          ["p.26 · Cl. 7.1", "Agency shall indemnify and keep NABARD indemnified"],
        ].map(([anchor, text], i) => {
          const e = interpolate(frame, [200 + i * 26, 224 + i * 26], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          return (
            <div key={anchor} style={{ display: "flex", gap: 22, alignItems: "center", opacity: e,
              transform: `translateX(${interpolate(e, [0, 1], [-16, 0])}px)` }}>
              <span style={{ fontFamily: T.mono, fontSize: 22, color: T.primary, width: 210 }}>{anchor}</span>
              <span style={{ fontFamily: T.display, fontSize: 26, color: T.inkSoft, fontWeight: 500 }}>{text}</span>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

/** Scene 3 — the denominator. The one claim no spreadsheet can make. */
export const Denominator: React.FC = () => {
  const frame = useCurrentFrame();
  const n = Math.round(interpolate(frame, [30, 110], [0, 57], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));
  return (
    <AbsoluteFill style={{ background: T.inverse, padding: 120, justifyContent: "center", color: T.onInverse }}>
      <Line size={44} color={T.onInverse} weight={600}>Every obligation sentence, counted.</Line>
      <div style={{ display: "flex", alignItems: "baseline", gap: 28, marginTop: 44 }}>
        <div style={{ fontFamily: T.display, fontSize: 210, fontWeight: 800, color: T.accent, letterSpacing: "-0.05em", lineHeight: 1 }}>
          {n}
        </div>
        <div style={{ fontFamily: T.display, fontSize: 40, fontWeight: 500, opacity: 0.85, maxWidth: 520, lineHeight: 1.25 }}>
          carried an obligation that no requirement covered yet
        </div>
      </div>
      <div style={{ marginTop: 46, opacity: interpolate(frame, [140, 170], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) }}>
        <span style={{ fontFamily: T.mono, fontSize: 22, letterSpacing: "0.08em", color: T.accent }}>
          NOTHING IS DROPPED QUIETLY
        </span>
      </div>
    </AbsoluteFill>
  );
};

/** Scene 4 — the artifact itself. Real screenshot, real numbers. */
export const Matrix: React.FC = () => {
  const frame = useCurrentFrame();
  const e = spring({ frame, fps: 30, config: { damping: 200, mass: 0.7 }, durationInFrames: 30 });
  // Slow push-in. Scale only, so it composites instead of re-laying-out every frame.
  const scale = interpolate(frame, [0, 300], [1.0, 1.06]);
  return (
    <AbsoluteFill
      style={{
        background: T.bg, alignItems: "center", justifyContent: "center",
        // Column layout with the chips as a real sibling, not an absolutely-positioned
        // overlay. Positioned absolutely they sat on top of the screenshot and clipped at the
        // frame edge, because the image is sized as a share of the canvas and the chips were
        // not part of that calculation.
        display: "flex", flexDirection: "column", gap: 40, padding: "70px 90px",
      }}
    >
      <div style={{ opacity: e, transform: `translateY(${interpolate(e, [0, 1], [26, 0])}px) scale(${scale})`,
        borderRadius: 20, overflow: "hidden", border: `1px solid ${T.hairline}`,
        boxShadow: "0 30px 90px rgba(0,82,204,0.18)", maxWidth: "80%", maxHeight: "74%" }}>
        <Img src={staticFile("matrix.png")} style={{ display: "block", width: "100%", height: "100%", objectFit: "contain" }} />
      </div>

      <div style={{ display: "flex", gap: 16 }}>
        {["Assign", "Track", "Export to Excel", "Re-import"].map((label, i) => {
          const on = interpolate(frame, [90 + i * 24, 112 + i * 24], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          return (
            <span key={label} style={{ fontFamily: T.display, fontSize: 25, fontWeight: 600,
              padding: "13px 26px", borderRadius: 999, background: T.surface, color: T.primary,
              border: `1px solid ${T.hairline}`, boxShadow: "0 8px 26px rgba(0,82,204,0.10)",
              opacity: on, transform: `translateY(${interpolate(on, [0, 1], [12, 0])}px)`, whiteSpace: "nowrap" }}>
              {label}
            </span>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

/** Scene 5 — cite or flag. The product's actual position. */
export const Cite: React.FC = () => {
  const frame = useCurrentFrame();
  const rows = [
    { text: "Meridian has completed 4 water metering projects above Rs. 1 Cr.", tag: "CITED", ok: true, src: "completion-certs.pdf · p.3" },
    { text: "Average annual turnover of Rs. 8.2 Cr across FY23 to FY25.", tag: "CITED", ok: true, src: "ca-certificate.pdf · p.1" },
    { text: "ISO 9001:2015 certification valid on the submission date.", tag: "FLAGGED", ok: false, src: "expired 03/2026 · no source" },
  ];
  return (
    <AbsoluteFill style={{ background: T.bg, padding: 120, justifyContent: "center" }}>
      <Line size={48} weight={700}>Every claim points at a document you own.</Line>
      <div style={{ marginTop: 52, display: "flex", flexDirection: "column", gap: 18 }}>
        {rows.map((r, i) => {
          const on = interpolate(frame, [30 + i * 40, 56 + i * 40], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          const tone = r.ok ? T.primary : T.accent;
          return (
            <div key={r.text} style={{ opacity: on, transform: `translateY(${interpolate(on, [0, 1], [14, 0])}px)`,
              background: T.surface, border: `1px solid ${T.hairline}`, borderRadius: 16, padding: "24px 28px",
              display: "flex", alignItems: "center", gap: 26, boxShadow: "0 10px 30px rgba(0,82,204,0.06)" }}>
              <span style={{ fontFamily: T.mono, fontSize: 18, letterSpacing: "0.08em", color: tone,
                border: `1px solid ${tone}`, borderRadius: 999, padding: "7px 15px", whiteSpace: "nowrap" }}>
                {r.tag}
              </span>
              <span style={{ fontFamily: T.display, fontSize: 28, fontWeight: 500, color: T.ink, flex: 1 }}>{r.text}</span>
              <span style={{ fontFamily: T.mono, fontSize: 18, color: T.inkSoft, whiteSpace: "nowrap" }}>{r.src}</span>
            </div>
          );
        })}
      </div>
      <div style={{ marginTop: 44, opacity: interpolate(frame, [190, 220], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }) }}>
        <span style={{ fontFamily: T.display, fontSize: 32, fontWeight: 600, color: T.inkSoft }}>
          What it cannot source, it flags. It never invents.
        </span>
      </div>
    </AbsoluteFill>
  );
};

/** Scene 6 — the close. */
export const Close: React.FC = () => {
  const e = useEnter(4);
  return (
    <AbsoluteFill style={{ background: T.inverse, justifyContent: "center", alignItems: "center", color: T.onInverse }}>
      <div style={{ opacity: e, transform: `translateY(${interpolate(e, [0, 1], [18, 0])}px)`, textAlign: "center" }}>
        <div style={{ fontFamily: T.display, fontSize: 92, fontWeight: 800, letterSpacing: "-0.04em" }}>
          TenderCraft <span style={{ color: "#5b9bff" }}>AI</span>
        </div>
        <div style={{ marginTop: 26, fontFamily: T.display, fontSize: 34, fontWeight: 400, opacity: 0.82 }}>
          Try it on your own tender.
        </div>
        <div style={{ marginTop: 40, fontFamily: T.mono, fontSize: 25, letterSpacing: "0.07em", color: T.accent }}>
          tendercraft.aisewak.com
        </div>
      </div>
    </AbsoluteFill>
  );
};
