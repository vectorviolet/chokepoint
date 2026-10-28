# 0005. Panel content independent of its placement
<!-- index | refs: #33 -->

- **Status:** Accepted
- **Date:** 2026-10-27
- **Issues / PRs:** [#33](https://github.com/vectorviolet/chokepoint/issues/33); applies to [#31](https://github.com/vectorviolet/chokepoint/issues/31) and [#32](https://github.com/vectorviolet/chokepoint/issues/32)

## Context

Issue #33 compared two homes for the info panels: a floating HUD overlay (A, the current one) and an
opaque sidebar (B), with mock-ups (see the
[devlog entry](../devlog/2026-10-27-info-panel-placement.md)). The owner chose A **for now** and
said it may be revisited. Upcoming work (#31 panel visuals, #32 Upgrade/Sell inside the panel) would
otherwise tie the panel's content to the overlay layout and make a later switch a rewrite.

## Decision

- The panel's content (rows, values, buttons) is one component that doesn't know where it is
  hosted.
- Its position and size come from `config/panels.yaml` only (the `tower_info_*` objects), not from
  code.
- #31 and #32 are built this way.

## Consequences

- Switching to a sidebar later means a new layout entry in `config/panels.yaml` plus the camera
  viewport and edge-scroll change that option B needs, not a rewrite of the panel.
- Panel code must not hard-code screen positions or assume it sits over the map. Fit tests at every
  window size stay layout-driven.
- The camera viewport is still the whole canvas; nothing in the camera prepares for a sidebar yet.

## Alternatives considered

- **Build #31 and #32 directly for the overlay:** simpler today, but a sidebar later would need the
  panel rebuilt.
- **Switch to the sidebar now:** the owner chose A for now.
