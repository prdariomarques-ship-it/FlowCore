# FlowCore Design System (Stitch / DESIGN.md)

This document specifies the design system rules, visual tokens, components, and layout principles for FlowCore's Investment Copilot interface, engineered using Google Stitch principles.

## 1. Visual Identity & Theme
- **Theme:** High-Resolution Dark Glassmorphism
- **Background:** `#060a17` with radial gradient ambient glows (`#7c3aed` @ 12% opacity top-left, `#00d4ff` @ 10% opacity bottom-right).
- **Glass Panel Surface:** `rgba(13, 21, 39, 0.75)` with `backdrop-filter: blur(16px)` and subtle border `rgba(30, 58, 95, 0.6)`.

## 2. Color Palette
- **Primary Accent (Cyan Glow):** `#00d4ff` | Glow: `rgba(0, 212, 255, 0.35)`
- **Secondary Accent (Deep Violet):** `#7c3aed` | Glow: `rgba(124, 58, 237, 0.35)`
- **Success (Emerald Green):** `#10b981` | Glow: `rgba(16, 185, 129, 0.35)`
- **Warning (Amber Gold):** `#f59e0b` | Glow: `rgba(245, 158, 11, 0.35)`
- **Critical / Danger (Crimson Red):** `#ef4444` | Glow: `rgba(239, 68, 68, 0.35)`
- **Text Primary:** `#f1f5f9`
- **Text Secondary:** `#94a3b8`

## 3. Typography
- **Primary Font:** `'Plus Jakarta Sans'`, sans-serif (Weights: 400, 500, 600, 700, 800)
- **Monospace Font:** `'JetBrains Mono'`, monospace (Weights: 400, 600, 800) for numeric financial values, percentages, and diffs.

## 4. Key Components
- **Compliance Alert Cards:** Glassmorphic card with colored left accent indicator (`#ef4444` for Critical, `#f59e0b` for Warning), progress track showing current allocation % vs teto limit % with glowing vertical marker.
- **Summary Chips:** 3-column metric grid displaying Critical count, Warning count, and Total affected portfolios.
- **Header:** Sticky header with blurred backdrop, gradient logo mark, animated status dot, and refresh trigger.
- **Bottom Navigation:** Fixed bottom bar with blurred glass backdrop, active neon accents, and mobile FAB drawer trigger.
