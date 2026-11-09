# Map obstacles and blocked build tiles
<!-- index | refs: #166, PR #167 -->

**Date:** 2026-11-07 · **Area:** Gameplay, rendering · **Issue:** [#166](https://github.com/vectorviolet/chokepoint/issues/166) · **PR:** [#167](https://github.com/vectorviolet/chokepoint/pull/167)

## Context

The owner placed trees and rocks in an `Obstacles` object group in the Tiled map
and asked for a review of their rendering and placement blocking. The initial
loader found tile images, but the draw code subtracted grid indices from pixel
positions. That shifted each image away from its blocked cell. A rectangle with
no image was also ignored, leaving its cell available for construction.

## Options

<table>
<tr>
<td><img src="img/166-obstacles-offset.png" width="480" alt="Initial obstacle positions shifted above and left of the blocked cells"><br>Initial approach: subtract grid indices while baking obstacles.</td>
<td><img src="img/166-obstacles-aligned.png" width="480" alt="Corrected obstacle positions aligned with their blocked cells"><br>Chosen approach: use the loaded pixel positions and block the full bounds.</td>
</tr>
</table>

These are cropped map previews rendered from the actual TMX and tileset, with red
outlines showing obstacle blockers. They illustrate the coordinate change; they
are not screenshots of a running game. The empty outlined cell in the corrected
preview is an image-less rectangle (object 101) that the owner later removed from
the shipped map; the code and tests still support such rectangles.

Drawing obstacles individually every frame would support moving objects, but the
current obstacles are static. They can share the existing map surface and camera
scale cache.

## Decision

The owner authorized the correction and the obstacle feature. Keep the authored
layout and existing tileset, load obstacle bounds independently of images, and
include static obstacle images in the game's `pre_render()` override.

`pytmx` already converts a tile object's bottom anchor to its top-left position.
Use those coordinates directly, without subtracting a tile height again or
changing the saved position during drawing. Resize tile images once when their
authored bounds differ from the source tile size.

For construction, block every grid cell intersecting an obstacle's bounds.
The right and bottom edges are exclusive, so a rectangle ending exactly at a
tile boundary does not block the next tile. Clip coverage to the map. Image-less
rectangles block construction without drawing a sprite. Images are drawn at the
floor of the bounds' top-left corner and sized to the same cells blocking uses.

The supported authoring convention is unrotated tile objects and rectangles in
the `Obstacles` group. Rotation, polygons, polylines, ellipses and points fail an
assert at load instead of being guessed at. Zero-area objects are ignored: they
neither draw nor block, as the issue says. A hidden group or object is skipped for drawing and blocking, like a
hidden tile layer.

Decisions made by the owner during review:

- The image-less rectangle (object 101) is removed from the shipped map.
- Towers in an old save that stand on a cell the map now blocks are removed when
  the save loads, and refunded in full (purchase plus upgrades, not the 70% sale
  refund). The alternatives were keeping them in place and hiding the obstacle
  under them. One line is logged with how many were refunded. Planes are
  unaffected, and no sell sound or effect plays on load.
- Obstacles are a 1.1 feature, but the owner allowed this PR to merge before 1.0
  despite the feature freeze.

## Result

Ground-tower placement and its existing preview use the updated buildable grid.
The menu demo uses the same grid when choosing tower positions. The enemy path
and plane placement rules keep their existing behavior. Obstacles are drawn
above the ground and below towers through the normal cached map draw.

Regression tests cover tile position and size, image-less rectangles, fractional
and multi-cell bounds, map edges, hidden groups and objects, unsupported shapes,
repeated rendering, camera zoom, and the old-save refund. Existing
menu-demo tests check that its towers stand only on buildable cells.

The targeting comparison runs on the real map grid. Seeds 1 and 7 both still make
tanks fire there (seed 3 no longer did after the layout change, so it was replaced).
All tests and simulations use temporary saves.

Paying to clear obstacles and saving cleared state remain in [#20](https://github.com/vectorviolet/chokepoint/issues/20).
Old saves are handled on load as described above.
