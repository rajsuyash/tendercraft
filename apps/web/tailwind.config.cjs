/**
 * Tailwind theme wired from the approved design contract (design/tokens.json).
 * Tokens are the ONLY source of color/type/spacing (docs/conventions.md) — hardcoded
 * hexes/font stacks fail /design-review. Fonts come through CSS vars set by next/font.
 *
 * The fontSize / borderRadius / boxShadow scales below are deliberately REDEFINED rather
 * than given new names: `text-sm`, `rounded-card` and friends are already used across every
 * component, so remapping what they resolve to restyles the whole app from one file instead
 * of touching ~40 components. That is why the iOS restyle is a token change.
 */
const tokens = require("../../design/tokens.json");

/** px -> rem, so the scale still respects a user's browser font-size setting. */
const rem = (px) => `${px / 16}rem`;

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: tokens.color.primary,
          hover: tokens.color["primary-hover"],
          tint: tokens.color["primary-tint"],
        },
        "on-primary": tokens.color["on-primary"],
        surface: { DEFAULT: tokens.color.surface, alt: tokens.color["surface-alt"] },
        border: tokens.color.border,
        ink: tokens.color.text,
        muted: tokens.color["text-muted"],
        success: { DEFAULT: tokens.color.success, bg: tokens.color["success-bg"] },
        danger: { DEFAULT: tokens.color.danger, bg: tokens.color["danger-bg"] },
        warning: { DEFAULT: tokens.color.warning, bg: tokens.color["warning-bg"] },
        info: { DEFAULT: tokens.color.info, bg: tokens.color["info-bg"] },
      },
      fontFamily: {
        heading: ["var(--font-heading)", "sans-serif"],
        body: ["var(--font-body)", "sans-serif"],
        mono: ["var(--font-mono)", "monospace"],
      },
      // The iOS text styles. The negative tracking at the top end is most of what makes SF
      // look like SF — without it, large headings read generic.
      fontSize: {
        "2xs": [rem(11), { lineHeight: "1.35" }],
        xs: [rem(12), { lineHeight: "1.4" }],
        sm: [rem(15), { lineHeight: "1.5" }],
        base: [rem(17), { lineHeight: "1.5" }],
        lg: [rem(20), { lineHeight: "1.35", letterSpacing: "-0.01em" }],
        xl: [rem(22), { lineHeight: "1.3", letterSpacing: "-0.015em" }],
        "2xl": [rem(28), { lineHeight: "1.25", letterSpacing: "-0.021em" }],
        "3xl": [rem(34), { lineHeight: "1.2", letterSpacing: "-0.024em" }],
      },
      borderRadius: {
        DEFAULT: `${tokens.radius.default}px`,
        card: `${tokens.radius.card}px`,
        sheet: `${tokens.radius.sheet}px`,
      },
      boxShadow: {
        sm: tokens.elevation.sm,
        card: tokens.elevation.card,
        lifted: tokens.elevation.lifted,
      },
      transitionTimingFunction: { ios: tokens.motion.ease },
      transitionDuration: {
        fast: tokens.motion["duration-fast"],
        DEFAULT: tokens.motion.duration,
        slow: tokens.motion["duration-slow"],
      },
      backdropBlur: { chrome: "20px" },
      spacing: {
        sidebar: `${tokens.space["sidebar-width"]}px`,
        page: `${tokens.space["page-padding"]}px`,
        card: `${tokens.space["card-padding"]}px`,
      },
      screens: {
        sm: `${tokens.breakpoints.sm}px`,
        md: `${tokens.breakpoints.md}px`,
        lg: `${tokens.breakpoints.lg}px`,
        xl: `${tokens.breakpoints.xl}px`,
      },
    },
  },
  plugins: [],
};
