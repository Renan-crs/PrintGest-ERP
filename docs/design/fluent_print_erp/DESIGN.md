---
name: Fluent Print ERP
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#434655'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#737686'
  outline-variant: '#c3c6d7'
  surface-tint: '#0053db'
  primary: '#004ac6'
  on-primary: '#ffffff'
  primary-container: '#2563eb'
  on-primary-container: '#eeefff'
  inverse-primary: '#b4c5ff'
  secondary: '#006591'
  on-secondary: '#ffffff'
  secondary-container: '#39b8fd'
  on-secondary-container: '#004666'
  tertiary: '#632ecd'
  on-tertiary: '#ffffff'
  tertiary-container: '#7d4ce7'
  on-tertiary-container: '#f6edff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dbe1ff'
  primary-fixed-dim: '#b4c5ff'
  on-primary-fixed: '#00174b'
  on-primary-fixed-variant: '#003ea8'
  secondary-fixed: '#c9e6ff'
  secondary-fixed-dim: '#89ceff'
  on-secondary-fixed: '#001e2f'
  on-secondary-fixed-variant: '#004c6e'
  tertiary-fixed: '#e9ddff'
  tertiary-fixed-dim: '#d0bcff'
  on-tertiary-fixed: '#23005c'
  on-tertiary-fixed-variant: '#5516be'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
typography:
  display-sm:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 20px
  body-lg:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-md:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  label-lg:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 16px
  label-md:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.03em
  label-sm:
    fontFamily: Inter
    fontSize: 10px
    fontWeight: '600'
    lineHeight: 12px
    letterSpacing: 0.04em
  data-mono-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '700'
    lineHeight: 24px
    letterSpacing: -0.02em
  data-mono-md:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
  data-mono-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 0.75rem
  margin: 1rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1rem
  space-xl: 1.5rem
---

## Brand & Style

This design system establishes an industrial, high-density desktop operating environment engineered specifically for print shop operations (gráfica rápida) implemented via PySide6 / Qt and modern Windows shell standards.

### Brand Personality & Philosophy
- **Precision & Reliability:** Reflects the mission-critical rhythm of counter-service operations, commercial order routing, and live press management.
- **Utilitarian Speed:** Eliminates gratuitous decoration. Every visual unit communicates status, hierarchy, or direct mechanical interaction. Keyboard efficiency is paramount; mouse movement is treated as an operational overhead.
- **Fluent Desktop Modernism:** Blends Windows 11 Fluent ergonomics (subtle layering, deliberate stroke boundaries, compact typography, immediate feedback) with enterprise-grade data density.

### Visual Atmosphere
The interface remains crisp, calm, and neutral under fluorescent shop lighting. Clean slate canvases prevent eye fatigue during 10-hour shifts, while chromatic accents directly evoke the CMYK print spectrum for rapid situational awareness.

## Colors

The palette balances clinical legibility with domain-specific color references from print production.

### Primary, Secondary & Domain Accents
- **Primary (`#2563EB`):** Core interactive focus, primary actions, active navigation tabs, and system state confirmation.
- **Secondary (`#0EA5E9`):** Cyan process cue, auxiliary toggles, subtotal emphasis, and telemetry indicators.
- **Tertiary (`#8B5CF6`):** "In Production" job states, prepress routing badges, and spooling cues.
- **CMYK Accents:** Deliberately reserved for visual badge indicators across production queues: Cyan (`#0EA5E9`), Magenta (`#EC4899`), Yellow (`#EAB308`), and Key/Black (`#0F172A`).

### Surfaces & Neutrals
- **App Canvas Background:** `#F1F5F9` (Slate 100) — Low-glare foundational substrate.
- **Panel / Window Surface:** `#FFFFFF` — High-clarity primary container.
- **Elevated Flyout / Popover:** `#FFFFFF` with structured border `#CBD5E1`.
- **Structural Stroke / Hairline:** `#E2E8F0` (Default borders), `#CBD5E1` (Input boundaries and active splitters).
- **Text Heavy:** `#0F172A` (Slate 900) for primary headlines, data values, and unit prices.
- **Text Muted:** `#475569` (Slate 600) for field labels, table headers, and structural metadata.

### Operational Status Tokens
- **Success / Cash Register Open / License Active:** Emerald `#059669` (Text/Icon on `#ECFDF5` container with `#A7F3D0` border).
- **Warning / Read-Only / Expiring License:** Amber `#D97706` (Text/Icon on `#FFFBEB` container with `#FDE68A` border).
- **Critical / Offline Local API / Blocked Order:** Carmim Red `#DC2626` (Text/Icon on `#FEF2F2` container with `#FECACA` border).
- **Local Daemon (127.0.0.1 / Token Live):** Emerald pill badge `#059669` with steady pulse; flashes Amber `#D97706` on retry queue.

## Typography

The typography is built around strict metric predictability and optical clarity across desktop monitor resolutions (primarily 1080p and 768p standard business displays).

### Numerical Figures & Tabular Columns
- All financial sums, job order numbers (e.g., `OS #10492`), paper weight values (`gsm`), sheet dimensions, and timestamps must render with OpenType Tabular Figures enabled (`font-feature-settings: "tnum"` / `font-variant-numeric: tabular-nums`). This prevents column jitter during real-time cost computation.

### Keyboard Accelerator Badges (`Kbd`)
- Key bindings (such as `[F2]`, `[Enter]`, `[Esc]`, `[Ctrl+P]`) are styled as inline mini-hardware indicators: 11px uppercase, bold weight (`600`), bordered in `#CBD5E1`, rendered inside a `#F8FAFC` cap with a 1px baseline offset for instantaneous peripheral recognition.

## Layout & Spacing

This design system utilizes an ergonomic, density-first desktop layout built to balance high information throughput with zero accidental clicks at the counter.

### Desktop Form Factors & Grids
- **Standard POS/Counter Canvas (1366x768):** Uses a consolidated 2-column or split 3-pane workspace with fixed toolbars and minimal edge margins (`12px` / `0.75rem`).
- **Full Operational Station (1920x1080):** 12-column fluid master-detail layout with a static left operational tree (240px width), dynamic data grid, and persistent right-hand order totals summary (340px width).
- **Z-Index Layering:**
  1. Main window workspace canvas.
  2. Docked toolbars & bottom hardware telemetry bar.
  3. Modal dialogs and print queue drawers.
  4. Quick lookup overlays (e.g., fast product search activated via `F3`).

### Compact Rhythms
Grid units enforce an exact 4px sub-pixel rhythm. Row heights in tables default to 32px (dense mode for production logs) or 40px (counter checkout mode with touch/click comfort).

## Elevation & Depth

Visual hierarchy matches the structured spatial rules of Windows Fluent Design:

### Structural Outlines Over Drop Shadows
- Desktop productivity prioritizes razor-sharp 1px boundary lines (`#E2E8F0` and `#CBD5E1`) over heavy blur radiuses. This avoids visual noise when dozens of data cells and panels sit side-by-side.

### Layer Hierarchy
- **Level 0 (Application Window Background):** Solid `#F1F5F9`. Anchors the background without distracting high-frequency luminance.
- **Level 1 (Panels, Data Grids, Form Groups):** Solid `#FFFFFF`, framed with a 1px solid `#E2E8F0` stroke. Zero shadow.
- **Level 2 (Active Dropdowns, Context Menus, Tooltips):** Solid `#FFFFFF`, bordered with `#CBD5E1`, lifted by a controlled ambient shadow: `0 4px 12px rgba(15, 23, 42, 0.08)`.
- **Level 3 (Modal Dialogs & Emergency Confirmations):** Solid `#FFFFFF`, bordered with `#94A3B8`, cast over an overlay scrim (`rgba(15, 23, 42, 0.45)`) with an elevation shadow of `0 12px 28px rgba(15, 23, 42, 0.16)`.

## Shapes

The design system employs a **Soft** corner architecture (`roundedness: 1`), providing an authentic enterprise feel that remains crisp and professional.

### Curvature Tokens
- **Standard Controls (Inputs, Buttons, Badges, Tabs):** `4px` (`0.25rem`). Maintains neat horizontal grid lines while eliminating harsh square apexes.
- **Surface Containers (Panels, Data Cards):** `6px` (`0.375rem`) to frame sub-workspaces cleanly.
- **Modal Dialog Frames:** `8px` (`0.5rem`) outer shell with native OS window geometry alignment.
- **Status Pills / Tags:** `4px` (`0.25rem`) corner radius. Rounded pill shapes (full radius) are prohibited to conserve inline text space and uphold technical rigor.

## Components

### Buttons & Shortcut Integrations
- **Primary Action (Confirm Order / Emit NF-e / F5):**
  Solid `#2563EB` fill, white bold text. Right-aligned `Kbd` hint badge in semi-transparent white container. Hover: `#1D4ED8`. Active: `#1E40AF`.
- **Secondary / Action Tool (Add Item / F2):**
  Solid `#FFFFFF` fill, 1px `#CBD5E1` border, `#0F172A` text. Hover: `#F8FAFC` background with `#94A3B8` border.
- **Danger Action (Cancel OS / Void Sale / Esc):**
  White fill, `#EF4444` border, `#DC2626` text. Hover: `#FEF2F2` background.

### Input Fields & Search Bars
- **Height & Padding:** Fixed 34px height for standard desktop inputs. Internal horizontal padding of 8px.
- **Default State:** White background, 1px `#CBD5E1` border, `#0F172A` text.
- **Focus State:** 1px `#2563EB` border accompanied by an inner/outer 1px fluent accent glow (`box-shadow: 0 0 0 1px #2563EB`).
- **Prefix / Suffix Elements:** Monetary labels ("R$") and dimensional units ("mm", "g/m²") feature a muted `#64748B` tone on a subtle `#F8FAFC` anchored cell.

### Tables & Data Grids (Core Production Log)
- **Header:** 32px height, `#F8FAFC` background, `#475569` uppercase 11px font with bold sorting indicators (`▲`/`▼`).
- **Data Rows:** Alternating faint striping optional; standard state relies on clean 1px bottom divider `#F1F5F9`. Hover state illuminates the entire row with `#F1F5F9`.
- **Selected Row:** `#EFF6FF` background with a 3px vertical accent border `#2563EB` at the leftmost edge.

### Status Badges & Local API Connectivity
- **Structure:** 20px height, compact 6px horizontal padding, 4px border radius.
- **Local Service Daemon Indicator (PySide6 / Localhost Bridge):**
  - *Online / Token Valid:* `#DCFCE7` background, `#15803D` text, leading 6px static emerald circle dot. Label: `127.0.0.1:Online`.
  - *Offline / Reconnect Queue:* `#FEE2E2` background, `#B91C1C` text, leading 6px amber blinking dot. Label: `Local API:Offline`.

### Banners & Alert Strips
- **Read-Only / Standby Mode:** Top-pinned 32px banner spanning the main viewport. Solid `#FFFBEB` with bottom border `#FDE68A`. Amber icon with concise copy: *"Modo Leitura — Licença requer sincronização periódica [Sincronizar Agora - F9]"*.
- **License Status Warning:** Pinned right corner warning pill with remaining days displayed in monospace numbers.

### Desktop Dialog Frames
- Custom Qt frameless header bar styled to imitate Windows 11 Fluent dark-gray or clean-slate window headers, housing window control clusters (Minimize, Maximize, Close) with high-contrast active hitboxes.