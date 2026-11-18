"""Filesystem anchors that work both from source and inside a PyInstaller bundle.

The game loads `assets/` and `config/` with paths relative to the current
working directory (e.g. ``AssetPath`` yields ``"assets/images/..."`` and
``game.py`` opens ``"config/settings.yaml"``). That only holds when the process
runs from the project root.

When PyInstaller freezes the app, data files bundled via the spec's ``datas``
are unpacked next to the executable (onedir) or extracted to a temp dir
(onefile); either way their location is exposed as ``sys._MEIPASS``. To keep the
existing relative paths valid in both modes, ``__main__`` chdirs into
:func:`resource_root` at startup, and anything that must resolve a bundled path
without relying on the cwd uses :func:`resource_path`.

Implementation lives in ``pygamine.assets.paths`` -- shared with every sibling
project, since the logic has nothing project-specific in it. Re-exported
here so existing ``from util.paths import resource_root`` call sites don't
need to change.
"""

from __future__ import annotations

from pygamine import resource_root as resource_root, resource_path as resource_path
