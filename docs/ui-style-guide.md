# UI Style Guide

Covers UX-10, UX-13..UX-17, UX-20, UX-23..UX-24. Implementations live in `ui/theme.py`, `ui/control_styles.py`, `ui/components.py` and `ui/strings.py`.

## Tokens

- Material 3 derives the light/dark palette from the green accent `#2E7D5B`.
- `Tone` is semantic: neutral, ok, warning, error or muted. `theme.tone_color()` and `state_button_style()` map tones to theme colors; views do not supply ad-hoc colors.
- Warning amber is `#9A5B00` in light mode and `#FFB74D` in dark mode. The theme comment records approximate surface contrast; a full WCAG audit remains tracked by B-135.
- Spacing is 4, 8, 16, 24 and 32 dp. Radii are 16 dp for cards and 8 dp for chips/buttons.
- Type scale is centralized in `TYPE`: label 11, caption 12, body/unit 14, title 18, text value 22 and numeric value 32.
- KPI cards use a stable 156 dp height and 200 ms opacity transitions.

## Components and states

- `KpiCard` presents an uppercase label, icon, value/unit, quality badge and short caption. Detailed timestamps are in its tooltip.
- `StatusChip` always combines an icon with text; state is never conveyed by color alone.
- Stateful controls use `state_button_style()` and stable dimensions. Pending, unavailable, disabled, failed and uncertain states remain distinct.
- The Garage tab keeps relay state separate from its Trigger command; relay state is never interpreted as door position.
- The System tab masks the token field and uses a separate Sign out action.

## Layout and behavior

- Use Material 3 controls and theme tokens rather than inline magic dimensions or colors.
- Keep the Overview and party tabs server-ordered. Party content updates in place to avoid scroll or tab resets.
- Touch targets should be at least 48 dp. Keep copy concise, allow wrapping on small screens, and support font scaling.
- The shared Flet icon/splash artwork is centered with transparent exterior pixels. Android uses the configured navy adaptive-icon background. The in-app watermark is centered at 50% opacity and ignores pointer interaction.
- Respect reduced assumptions about state: render the server's quality and capability, never invent an off/zero state for missing data, and never optimistically change physical state.

## Strings

All user-facing labels and messages belong in `ui/strings.py`. Presentation metadata keyed by server id belongs in `domain/presentation.py`; this guide and views must not duplicate catalog labels.
