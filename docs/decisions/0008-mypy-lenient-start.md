# 0008. Type checking with mypy, a lenient start
<!-- index | refs: #37 -->

- **Status:** Accepted
- **Date:** 2026-11-02
- **Issues / PRs:** [#37](https://github.com/vectorviolet/chokepoint/issues/37)

## Context

The code has type hints, but nothing checked them: an `int` game time that was really a float,
a `render(..., 2, ...)` where a bool was meant, values that may be None used without a check.
The owner's own pass at these (issue #37) also showed the risk of the opposite fix: silent
`if not x: return` guards hide a broken invariant instead of reporting it. A strict checker on
the whole code at once would mean hundreds of changes in one PR.

## Decision

mypy runs on `src/` in CI ("Type check (mypy)", a separate job; not a required check until the
owner makes it one, which the owner did on 2026-11-03) and locally with `uv run --group dev mypy`. The config is `[tool.mypy]` in
`pyproject.toml`:

- Default (non-strict) checks: unannotated functions aren't checked. An import mypy can't
  resolve is an error, except for third-party modules without stubs (only `pytmx` for now, an
  override per module); PyYAML's stubs come from `types-pyyaml` in the dev group.
- The pygamine submodule is not checked here (it has its own CI), but its types are used
  (`follow_imports = "silent"`).
- Game's mixins (`app.game_events`, `app.game_save`) skip `attr-defined` and `has-type`: they use
  attributes that `Game` defines, which mypy can't see from the mixin.

Where mypy can't see that a value is set, the code says so with `assert x is not None` (or an
`isinstance` check), so a broken invariant fails loudly. None is handled for real only where it
can really happen; where a None came from stale state, the state goes instead (placement takes
its tile from the click, not from the last frame's cursor).
A `# type: ignore[code]` always names the error code and has its reason on the line above.
Game objects' `update()`/`draw()` take the battle's state, unlike pygamine's `GameObject`, so
they carry `ignore[override]`.

## Consequences

Type mistakes in new code show up in CI. The leniency is a starting point, not a goal: later
steps can turn on `check_untyped_defs`, type the mixins' `self` with a Protocol, and switch the
`SpriteRenderer2D` asserts to pygamine's `require_component` (pygamine#14) once it is released.
