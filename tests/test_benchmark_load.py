"""scripts/benchmark_load.py (issue #12) runs end to end at tiny counts and,
like the smoke test, never touches the real saves/."""

import importlib.util
from pathlib import Path

from pygamine import SaveStore

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "benchmark_load.py"


def _load_benchmark():
    spec = importlib.util.spec_from_file_location("benchmark_load", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_benchmark_runs_every_scenario_and_leaves_real_saves_unchanged(
    tmp_path, monkeypatch, capsys
):
    bench = _load_benchmark()
    sentinel = tmp_path / "real_saves"
    monkeypatch.setattr(SaveStore.__init__, "__defaults__", (str(sentinel),))
    sentinel.mkdir()
    (sentinel / "save.json").write_bytes(b'{"level": 7}')
    before = bench.snapshot(sentinel)
    monkeypatch.setattr(bench, "REAL_SAVES", sentinel)

    results = bench.main(
        [
            "--loads",
            "6x5",
            "--speeds",
            "1,4",
            "--zooms",
            "1,fit",
            "--frames",
            "3",
            "--warmup",
            "1",
            "--profile",
        ]
    )

    assert bench.snapshot(sentinel) == before
    assert [(r["speed"], r["zoom"]) for r in results] == [
        (1, "1"),
        (4, "1"),
        (1, "fit"),
        (4, "fit"),
    ]
    for r in results:
        assert (r["enemies"], r["towers"], r["frames"]) == (6, 5, 3)
        assert r["tick"]["mean"] > 0 and r["draw"]["mean"] > 0
    out = capsys.readouterr().out
    assert out.count("| 6 | 5 |") == 4
    assert "sorted by tottime" in out


def test_fps_max_accounts_for_ticks_per_frame():
    bench = _load_benchmark()
    assert bench.fps_max(0.0, 1.0) == bench.TICKS_PER_SECOND  # capped
    # 165 ticks of 2 ms leave 670 ms a second for 10 ms draws: 67 FPS.
    assert round(bench.fps_max(2.0, 10.0)) == 67
    assert bench.fps_max(1000 / bench.TICKS_PER_SECOND, 1.0) == 0.0  # slow motion
