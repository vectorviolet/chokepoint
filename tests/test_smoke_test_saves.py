"""scripts/smoke_test.py must never write to the real saves/ (issue #30)."""

import importlib.util
from pathlib import Path

from pygamine import SaveStore

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "smoke_test.py"


def _load_smoke_test():
    spec = importlib.util.spec_from_file_location("smoke_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_saves_redirected_points_savestore_at_a_temp_folder():
    smoke = _load_smoke_test()
    original = SaveStore.__init__.__defaults__
    with smoke.saves_redirected() as tmp_saves:
        store = SaveStore("settings")
        assert store.directory == tmp_saves
        assert store.directory.resolve() != Path("saves").resolve()
        store.save({"probe": 1})
        assert (tmp_saves / "settings.json").exists()
    assert SaveStore.__init__.__defaults__ == original
    assert not tmp_saves.exists()


def test_snapshot_detects_any_byte_change(tmp_path):
    smoke = _load_smoke_test()
    saves = tmp_path / "saves"
    assert smoke.snapshot(saves) is None
    saves.mkdir()
    (saves / "save.json").write_bytes(b"{}")
    before = smoke.snapshot(saves)
    assert smoke.snapshot(saves) == before
    (saves / "save.json").write_bytes(b"{ }")
    assert smoke.snapshot(saves) != before


def test_smoke_test_leaves_real_saves_unchanged(tmp_path, monkeypatch):
    """Runs the whole smoke test with SaveStore's default directory set to a
    sentinel "real saves" folder (holding a save and settings), so only the
    script's own redirect stands between its Game()s and that folder."""
    smoke = _load_smoke_test()
    sentinel = tmp_path / "real_saves"
    monkeypatch.setattr(SaveStore.__init__, "__defaults__", (str(sentinel),))
    sentinel.mkdir()
    (sentinel / "save.json").write_bytes(b'{"level": 7}')
    (sentinel / "settings.json").write_bytes(b'{"music": 0.3}')
    before = smoke.snapshot(sentinel)
    monkeypatch.setattr(smoke, "REAL_SAVES", sentinel)

    smoke.main()

    assert smoke.snapshot(sentinel) == before
