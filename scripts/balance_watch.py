"""Watching a balance-sim bot play (issue #100): `balance_sim.py --watch`.

A Watcher shows one StrategyRun in a game window, drawn by the game's own
draw path with its HUD, at real-time pace: the game's own update() runs one
tick per TICK_MS of real time, each moving game time on by TICK_MS times the
game speed, and every one of those ticks is a StrategyRun.step(), so the bot
plays exactly as it does headless while the speed stays at --game-speed.
Changing it with + or - changes each tick's motion and timing, so from then
on the run can differ from the headless one. The camera edge-scrolls and
zooms as in the game; nothing else the viewer does reaches the run.

Keys: Space pauses and resumes, + and - change the game speed (x1, x2, x4),
F toggles fast-forward (ticks as fast as the CPU allows, drawing a frame
every FAST_FORWARD_FRAME_MS), Esc or closing the window quits. When the run
ends the window stays open with a short summary.

The caller (balance_sim.watch()) redirects saves; nothing is written.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import pygame

from app.game_events import SPEED_BUTTON_STATES
from util.constants import GAME_SPEEDS

# Fast-forward: real time spent ticking between two drawn frames.
FAST_FORWARD_FRAME_MS = 50
SUMMARY_FONT_SIZE = 32
SUMMARY_PADDING = 32
SUMMARY_LINE_GAP = 8


def watched_game_class(base: type) -> type:
    """`base` (balance_sim's SimGame) with Game.update()'s ticks handed to
    the Watcher, which runs them as StrategyRun steps (or drops them while
    paused or once the run has ended)."""

    class WatchedGame(base):  # type: ignore[valid-type, misc]
        on_tick: Callable[[], None] | None = None

        def _tick(self) -> None:
            assert self.on_tick is not None, "Watcher sets on_tick"
            self.on_tick()

    return WatchedGame


class Watcher:
    """Plays `run` (a StrategyRun whose game is a watched_game_class()) in
    its game's window. `summary()` gives the lines shown once it ends."""

    def __init__(self, run, summary: Callable[[], list[str]]) -> None:
        self.run = run
        self.game = game = run.game
        self._summary = summary
        self.paused = False
        self.fast_forward = False
        self.running = True
        self.frames = 0  # frames drawn
        self._summary_panel: pygame.Surface | None = None  # once the run ends
        game.on_tick = self._tick
        # A normal window, whatever the (redirected, empty) settings say.
        # Not under the dummy driver (tests): nothing is shown, and its
        # "screen" is the last window opened, so each windowed run would
        # shrink the next one's.
        if pygame.display.get_driver() != "dummy":
            game.set_windowed()
        self._title = f"{game.get_title()}: watching {run.result.strategy}"
        self._refresh_title()
        self._refresh_speed_button()
        self._font = pygame.font.Font(
            str(game.assets.font_path("anton")), SUMMARY_FONT_SIZE
        )

    # ── the run ──────────────────────────────────────────────────────────────

    def _tick(self) -> None:
        if not self.paused and not self.run.finished:
            self.run.step()

    def _fast_forward(self) -> None:
        """Ticks on for FAST_FORWARD_FRAME_MS of real time."""
        until = time.perf_counter() + FAST_FORWARD_FRAME_MS / 1000
        while not self.paused and not self.run.finished:
            self.run.step()
            if time.perf_counter() >= until:
                break

    # ── input ────────────────────────────────────────────────────────────────

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.MOUSEWHEEL:
            self.game.camera.handle_event(event, self.game.mouse.position)
        elif event.type == pygame.KEYDOWN:
            self._handle_key(event)

    def _handle_key(self, event: pygame.event.Event) -> None:
        key = event.key
        text = getattr(event, "unicode", "")
        if key == pygame.K_ESCAPE:
            self.running = False
        elif key in (pygame.K_F1, pygame.K_F11):
            # The game's own debug overlay and window-mode keys.
            self.game._handle_core_event(event)
        elif key in (pygame.K_SPACE, pygame.K_f) and self.run.finished:
            pass  # nothing left to pause or fast-forward
        elif key == pygame.K_SPACE:
            self.paused = not self.paused
            self._refresh_title()
            # The HUD's start/pause button shows it, as in the game.
            self.game.panel_manager["game"]["start_pause_button_icon"].set_state(
                None if self.paused else "pause"
            )
        elif key == pygame.K_f:
            self.fast_forward = not self.fast_forward
            self._refresh_title()
        elif text == "+" or key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
            self._change_speed(+1)
        elif text == "-" or key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            self._change_speed(-1)

    def _change_speed(self, step: int) -> None:
        """One step up or down GAME_SPEEDS, stopping at either end."""
        gs = self.game.game_state
        index = GAME_SPEEDS.index(gs.speed) + step
        gs.speed = GAME_SPEEDS[max(0, min(len(GAME_SPEEDS) - 1, index))]
        self._refresh_speed_button()

    def _refresh_speed_button(self) -> None:
        self.game.panel_manager["game"]["speed_toggle_button"].set_state(
            SPEED_BUTTON_STATES[self.game.game_state.speed]
        )

    def _refresh_title(self) -> None:
        state = " (paused)" if self.paused else ""
        state += " (fast-forward)" if self.fast_forward else ""
        pygame.display.set_caption(self._title + state)

    # ── frames ───────────────────────────────────────────────────────────────

    def loop(self, frames: int | None = None) -> None:
        """Runs until Esc or the window is closed (or `frames` are drawn)."""
        while self.running and (frames is None or self.frames < frames):
            self.frame()

    def frame(self) -> None:
        """One frame of pygamine's Application.run() loop (clock, inputs,
        events, update, draw, mouse, debug, present) with the watcher's own
        keys and fast-forward. Application.run() has no per-frame hook to
        call, so this copies its body: keep the two in step."""
        game = self.game
        # Fast-forward draws as often as it can while there is something to
        # tick; otherwise the game's own frame cap.
        ticking = self.fast_forward and not self.paused and not self.run.finished
        game.clock.tick(0 if ticking else game._fps)
        game._listen_inputs()
        for event in pygame.event.get():
            self.handle_event(event)
        game.update()  # camera, HUD, effects, and the run's real-time ticks
        if ticking:
            self._fast_forward()
        if self.run.finished and self._summary_panel is None:
            self._finish()
        game.draw()
        if self._summary_panel is not None:
            canvas = game.window
            canvas.blit(
                self._summary_panel,
                self._summary_panel.get_rect(center=canvas.get_rect().center),
            )
        game.draw_mouse()
        if game._is_in_debug_mode:
            game.draw_debug()
        game._present()
        self.frames += 1

    def _finish(self) -> None:
        """Once, as the run is first seen to have ended: the summary
        replaces the game-over popup (whose buttons do nothing here), and
        there is nothing left to pause or fast-forward."""
        self.game._set_gameover_popup_active(False)
        self.paused = self.fast_forward = False
        self._refresh_title()
        self._summary_panel = self._render_summary()

    def _render_summary(self) -> pygame.Surface:
        lines = [
            self._font.render(line, True, (255, 255, 255)) for line in self._summary()
        ]
        width = max(line.get_width() for line in lines) + 2 * SUMMARY_PADDING
        height = (
            sum(line.get_height() for line in lines)
            + SUMMARY_LINE_GAP * (len(lines) - 1)
            + 2 * SUMMARY_PADDING
        )
        panel = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.rect(panel, (0, 0, 0, 200), panel.get_rect(), border_radius=12)
        y = SUMMARY_PADDING
        for line in lines:
            panel.blit(line, line.get_rect(midtop=(width // 2, y)))
            y += line.get_height() + SUMMARY_LINE_GAP
        return panel
