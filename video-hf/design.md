# TenderCraft — video design system

Authored for the demo film. Colors and type come from the product's own marketing language
(`apps/web/app/(marketing)/marketing.css`), so the film and the site read as one brand.

## Colors

| Role | Hex | Use |
|---|---|---|
| bg | `#faf8ff` | light canvas, default |
| bg-deep | `#101728` | inverted scenes (the two claim scenes) |
| surface | `#ffffff` | cards, panels |
| ink | `#131b2e` | headlines on light |
| ink-soft | `#434654` | body on light |
| on-inverse | `#eef0ff` | text on bg-deep |
| primary | `#0052cc` | focal accent, figures, rules |
| primary-deep | `#003d9b` | gradient partner, deep fills |
| primary-tint | `#dae2ff` | atmospheric washes, ghost type |
| accent | `#ff9933` | saffron. Reserved for ONE thing per scene. |
| hairline | `#c9cee6` | structural rules at video weight (2px, not 1px) |

## Typography

- Display: **Geist**, 700/800. Headlines 72-120px. Letter-spacing -0.03em.
- Body: **Inter**, 400/500. 30-42px.
- Data / labels: **JetBrains Mono**, 500. 20-26px, letter-spacing 0.1em, uppercase.

Numbers use `font-variant-numeric: tabular-nums` so counters do not jitter.

## Personality

Precise, load-bearing, unhurried. The reference object is a well-kept engineering logbook:
ruled, dated, initialled in the margin. Motion is confident and slightly slow. Nothing bounces.

## Do

- Anchor content to an edge. Left-aligned with a wide right margin is the house frame.
- Structural rules and registration marks. Ruled lines carry this brand.
- One saffron hit per scene, at full saturation. It marks the single number that matters.
- Ghost type and grid texture behind content. A flat panel reads as an unfinished slide.

## Do NOT

- Bounce, elastic or overshoot easing. This product sells not being surprised.
- Purple/violet "AI" gradients. Category cliché, and not in the palette.
- Saffron on more than one element in a frame. It stops meaning anything.
- Centered floating content with air on both sides. That is a web layout, not a frame.
- Flat solid backgrounds with no texture.
