/**
 * Tailwind theme wired from the approved design contract (design/tokens.json).
 *
 * Per docs/conventions.md, tokens are the ONLY source of color/type/spacing values —
 * hardcoded hexes and font stacks fail review. This config is the single mapping point:
 * change a token, the whole UI follows. Consumed once Next.js + Tailwind land (M0 T6–T8).
 */
import tokens from "../../design/tokens.json" with { type: "json" };

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: { DEFAULT: tokens.color.primary, hover: tokens.color["primary-hover"], tint: tokens.color["primary-tint"] },
        surface: { DEFAULT: tokens.color.surface, alt: tokens.color["surface-alt"] },
        border: tokens.color.border,
        ink: tokens.color.text,
        muted: tokens.color["text-muted"],
        // Verdict semantics — reserved (design contract §C), never repurposed.
        success: { DEFAULT: tokens.color.success, bg: tokens.color["success-bg"] },
        danger: { DEFAULT: tokens.color.danger, bg: tokens.color["danger-bg"] },
        warning: { DEFAULT: tokens.color.warning, bg: tokens.color["warning-bg"] },
        info: { DEFAULT: tokens.color.info, bg: tokens.color["info-bg"] },
      },
      fontFamily: {
        heading: tokens.font.heading.split(",").map((s) => s.trim()),
        body: tokens.font.body.split(",").map((s) => s.trim()),
        mono: tokens.font.mono.split(",").map((s) => s.trim()),
      },
      borderRadius: {
        DEFAULT: `${tokens.radius.default}px`,
        card: `${tokens.radius.card}px`,
      },
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
