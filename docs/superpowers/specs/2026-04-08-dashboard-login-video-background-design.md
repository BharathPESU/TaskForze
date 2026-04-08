# Dashboard/Login Video Background Design

## Context

TaskForze frontend is a Next.js app where the primary UX surfaces are:
- `frontend/src/app/login/page.tsx` (login experience)
- `frontend/src/app/page.tsx` (main dashboard, wrapped by `AuthGuard`)

An MP4 background video already exists in the repository root public directory:
- `public/Futuristic_AI_Workspace_Video_Generation.mp4`

The user requested adding this video as background UI for both pages without affecting existing features.

## Goals

1. Apply a video background to both login and dashboard pages.
2. Preserve all existing behavior (auth, API calls, state, interactions).
3. Keep readability and visual hierarchy intact with overlays.
4. Include reduced-motion fallback for accessibility.
5. Minimize blast radius and keep implementation maintainable.

## Non-Goals

1. Redesigning page content, layout structure, or feature workflows.
2. Modifying backend APIs, auth logic, or route behavior.
3. Replacing or deleting existing static background assets globally.

## Selected Approach

Approach A: Shared reusable background component, integrated in both pages.

Why this approach:
- Reusable and clean (single source of truth for video background behavior).
- Low risk to existing code paths (UI-only layer, no business logic changes).
- Easy future tuning (opacity/overlay/perf in one file).

## File-Level Design

### New File

1. `frontend/src/components/BackgroundVideo.tsx`
   - Purpose: Render full-screen, non-interactive background video and visual overlays.
   - Responsibilities:
     - Render `<video>` with safe autoplay attributes.
     - Apply overlay gradients for readability.
     - Respect `prefers-reduced-motion` and fallback to static/non-video background layer.
     - Remain pointer-transparent and behind page content.

### Modified Files

1. `frontend/src/app/login/page.tsx`
   - Add `BackgroundVideo` near root container.
   - Preserve login card, error surfaces, and sign-in button behavior unchanged.

2. `frontend/src/app/page.tsx`
   - Add `BackgroundVideo` at top-level dashboard container under `AuthGuard`.
   - Keep sidebar/header/content layers unchanged, only ensuring z-index remains above background.

3. `frontend/src/app/globals.css` (if needed, minimal)
   - Keep current global styles.
   - Only add narrowly scoped helper class(es) if required for smooth fallback behavior.

### Asset Placement

1. Copy source video from:
   - `public/Futuristic_AI_Workspace_Video_Generation.mp4`
2. To frontend-served public directory:
   - `frontend/public/Futuristic_AI_Workspace_Video_Generation.mp4`

Rationale: Next.js serves static assets from `frontend/public`. This avoids route/proxy complexity.

## Component Behavior Specification

`BackgroundVideo` behavior:

1. Layout/layering
   - Outer wrapper: fixed/absolute full-viewport bounds.
   - `pointer-events: none` so no interaction interception.
   - Negative/low z-index to remain behind content.

2. Video playback attributes
   - `autoPlay`, `muted`, `loop`, `playsInline`.
   - `preload="metadata"` for balanced startup cost.
   - `object-cover` and centered positioning for responsive fill.

3. Readability overlays
   - Add dark gradient overlay to support high-contrast text in both pages.
   - Maintain existing visual style (glassmorphism cards still visible).

4. Reduced motion
   - Detect `prefers-reduced-motion: reduce`.
   - If reduce enabled, do not animate video playback (render static fallback layer).
   - Fallback layer uses existing dark gradient so content remains legible.

5. Progressive safety
   - No dependency on external runtime APIs.
   - If video fails to load, overlays still provide stable background.

## Error Handling

1. Video load failure should not break page render.
2. Component must degrade silently to overlay-only background.
3. No user-facing error banners for background media failures.

## Testing Strategy

Given current project has no formal frontend test suite, verification is manual + build checks:

1. Static checks
   - `cd frontend && npm run build`
   - Verify no TypeScript/Next build regressions.

2. Manual UX verification
   - Login page shows background video and retains sign-in controls.
   - Dashboard shows background video with all panels readable.
   - Sidebar/header buttons remain fully clickable.
   - Mobile viewport still renders correctly (video cover behavior).

3. Accessibility verification
   - With reduced-motion setting enabled, background is non-animated fallback.

## Rollback Plan

1. Remove `BackgroundVideo` usage from both page files.
2. Keep existing UI containers untouched.
3. Optionally keep component file for future use or remove if fully reverting.

## Risks and Mitigations

1. Risk: Text contrast degradation on bright frames.
   - Mitigation: conservative dark overlay and vignette.

2. Risk: Mobile performance overhead.
   - Mitigation: `preload="metadata"`, reduced-motion fallback, no heavy filters.

3. Risk: Z-index conflicts.
   - Mitigation: enforce explicit stacking (`relative z-10` on content roots only where required).

## Acceptance Criteria

1. Video appears as background on both login and dashboard.
2. Existing login and dashboard functionality remains unchanged.
3. UI remains readable across major sections.
4. Reduced-motion users do not receive animated background.
5. Frontend build passes successfully.
