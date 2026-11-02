TILE_SIZE = 64

# Clearing this wave triggers the victory popup once per run (config/waves.yaml
# keeps generating waves past it -- "Continue" just keeps playing those).
WIN_WAVE = 25
HALF_TILE = TILE_SIZE // 2

# Gameplay advances in fixed ticks, TICKS_PER_SECOND of them per real second
# whatever the display's frame rate. Per-tick quantities in the code and
# config (enemy speed, projectile speed, camera scroll, ...) are authored
# against this rate, which is the frame cap they were originally tuned at.
TICKS_PER_SECOND = 165
TICK_MS = 1000 / TICKS_PER_SECOND
# Longest stretch of real time a single frame may simulate. A longer stall
# (dragging the window, a breakpoint) is dropped rather than replayed in one
# burst of ticks.
MAX_FRAME_MS = 250
