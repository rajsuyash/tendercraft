---
name: TenderEvaluate AI
colors:
  surface: '#f7f9fb'
  surface-dim: '#d8dadc'
  surface-bright: '#f7f9fb'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f4f6'
  surface-container: '#eceef0'
  surface-container-high: '#e6e8ea'
  surface-container-highest: '#e0e3e5'
  on-surface: '#191c1e'
  on-surface-variant: '#43474e'
  inverse-surface: '#2d3133'
  inverse-on-surface: '#eff1f3'
  outline: '#74777f'
  outline-variant: '#c4c6cf'
  surface-tint: '#455f88'
  primary: '#002045'
  on-primary: '#ffffff'
  primary-container: '#1a365d'
  on-primary-container: '#86a0cd'
  inverse-primary: '#adc7f7'
  secondary: '#8f4e00'
  on-secondary: '#ffffff'
  secondary-container: '#fe9832'
  on-secondary-container: '#683700'
  tertiary: '#112235'
  on-tertiary: '#ffffff'
  tertiary-container: '#27374b'
  on-tertiary-container: '#90a0b9'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#d6e3ff'
  primary-fixed-dim: '#adc7f7'
  on-primary-fixed: '#001b3c'
  on-primary-fixed-variant: '#2d476f'
  secondary-fixed: '#ffdcc2'
  secondary-fixed-dim: '#ffb77a'
  on-secondary-fixed: '#2e1500'
  on-secondary-fixed-variant: '#6d3a00'
  tertiary-fixed: '#d3e4fe'
  tertiary-fixed-dim: '#b7c8e1'
  on-tertiary-fixed: '#0b1c30'
  on-tertiary-fixed-variant: '#38485d'
  background: '#f7f9fb'
  on-background: '#191c1e'
  surface-variant: '#e0e3e5'
typography:
  headline-xl:
    fontFamily: Geist
    fontSize: 48px
    fontWeight: '700'
    lineHeight: '1.1'
    letterSpacing: -0.04em
  headline-lg:
    fontFamily: Geist
    fontSize: 32px
    fontWeight: '600'
    lineHeight: '1.2'
    letterSpacing: -0.03em
  headline-lg-mobile:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: '1.2'
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Geist
    fontSize: 20px
    fontWeight: '600'
    lineHeight: '1.4'
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: '1.6'
    letterSpacing: 0.01em
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: '1.5'
    letterSpacing: 0.01em
  label-md:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '500'
    lineHeight: '1'
    letterSpacing: 0.05em
  code-sm:
    fontFamily: Geist
    fontSize: 13px
    fontWeight: '400'
    lineHeight: '1.5'
    letterSpacing: '0'
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  container-max: 1440px
  gutter: 24px
  margin-desktop: 48px
  margin-mobile: 16px
  unit-xs: 4px
  unit-sm: 8px
  unit-md: 16px
  unit-lg: 24px
  unit-xl: 48px
---

## Brand & Style

The design system is built on a foundation of **Modern Enterprise Professionalism**, blending the high-utility aesthetic of developer-centric tools like Stripe and Linear with a sophisticated institutional weight. The system evokes a sense of absolute precision, speed, and reliability—critical for AI-driven procurement and government contract evaluation.

The visual direction follows a **Refined Minimalism** approach. It utilizes expansive whitespace to reduce cognitive load, paired with high-performance UI elements that feel reactive and intelligent. Subtle glassmorphic layers are used to signify depth and modularity, while sharp, clear typography ensures the massive amounts of data handled by the platform remain legible and authoritative. The emotional response should be one of "effortless command" over complex information.

## Colors

The palette is anchored by **Deep Navy (#1A365D)**, used for primary actions, navigation, and core branding to establish institutional trust. **Saffron (#FF9933)** is employed as a high-intent accent color, used sparingly for status indicators, highlighting AI-generated insights, or critical "Call to Action" moments that require immediate user focus.

The background logic relies on a tiered system of whites and very light grays. The primary workspace is pure white (`#FFFFFF`), while sidebars and secondary containers use the neutral background (`#F8FAFC`) to create subtle structural boundaries without the need for heavy lines.

## Typography

This design system uses a dual-font strategy. **Geist** is used for headlines, labels, and technical data points to provide a clean, "developer-grade" precision. **Inter** is utilized for all body copy and long-form evaluation text to ensure maximum readability and a softer, more approachable feel for extended reading sessions.

Tracking (letter-spacing) is tightened slightly for large headings to create a dense, premium look, while body copy and labels receive generous tracking to enhance clarity on high-resolution displays.

## Layout & Spacing

The layout utilizes a **12-column fluid grid** for the main content area, with a fixed-width sidebar for navigation. We prioritize "generous breathing room"—whitespace is not just an aesthetic choice but a functional one to separate complex data modules.

- **Desktop:** 12 columns, 24px gutters, 48px outer margins.
- **Tablet:** 8 columns, 16px gutters, 24px outer margins.
- **Mobile:** 4 columns, 16px gutters, 16px outer margins.

The spacing rhythm is strictly based on an 8px base unit. Component internal padding should default to `unit-md` (16px) for standard elements and `unit-lg` (24px) for cards and sections.

## Elevation & Depth

Hierarchy is established through **Glassmorphism** and **Ambient Shadows**. Instead of heavy borders, surfaces are defined by their elevation.

1.  **Level 0 (Base):** The primary background color.
2.  **Level 1 (Cards/Modules):** White surface with a 1px border of `#E2E8F0` and a soft, highly diffused shadow: `0 4px 12px rgba(0, 0, 0, 0.03)`.
3.  **Level 2 (Overlays/Glass):** Semi-transparent white (`rgba(255, 255, 255, 0.7)`) with a `blur(12px)` backdrop filter. Used for sticky headers, floating menus, and modal backgrounds.
4.  **Level 3 (Active Modals):** White surface with a deep, dramatic shadow: `0 20px 40px rgba(26, 54, 93, 0.1)`.

All transitions between elevation states should be smooth (200ms ease-out).

## Shapes

The design system adopts a **Large Rounded** aesthetic to soften the technical nature of the application and create a modern, approachable atmosphere.

- **Standard Elements (Buttons, Inputs):** 0.5rem (8px).
- **Large Containers (Cards, Modals):** 1rem (16px).
- **Extra Large (Hero Sections, AI Insights):** 1.5rem (24px).

Interactive elements like checkboxes and radio buttons should maintain a consistent `rounded-sm` (4px) or full circle profile respectively.

## Components

### Buttons
- **Primary:** Solid `#1A365D` with white text. High-contrast, bold, and 48px height for main actions.
- **Secondary:** Saffron-tinted background (`#FFF7ED`) with `#FF9933` text for AI-related prompts.
- **Ghost:** Transparent background with subtle border, used for utility actions.

### Cards
Cards are the primary container. They must feature a `rounded-xl` radius, white background, and a soft ambient shadow. For "Featured" or "AI-Recommended" tenders, apply a subtle 1px border gradient using the secondary saffron color.

### Input Fields
Inputs use a `neutral-100` background with a `0.5rem` radius. On focus, the border transitions to the primary navy with a subtle outer glow (2px).

### Chips & Status Indicators
Status indicators (e.g., "Pending", "Approved", "Flagged") should use a "Pill" shape with low-saturation background tints and high-saturation text for readability.

### AI Insight Modules
These are specialized components with a slight glassmorphic backdrop and a left-accent border in Saffron to denote that the content was generated by "TenderEvaluate AI".