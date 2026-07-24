/**
 * Tailwind theme wired from the approved design contract (design/tokens.json).
 * Tokens are the ONLY source of color/type/spacing (docs/conventions.md) — hardcoded
 * hexes/font stacks fail /design-review. Fonts come through CSS vars set by next/font.
 */
const tokens = require("../../design/tokens.json");

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
      },
      borderRadius: { DEFAULT: `${tokens.radius.default}px`, card: `${tokens.radius.card}px` },
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
