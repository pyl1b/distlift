from __future__ import annotations

from distlift.plugins.base import DistliftPlugin


def build_builtin_plugins() -> list[DistliftPlugin]:
    """Return all built-in plugin instances."""
    from distlift.languages.javascript import JavaScriptProjectPlugin
    from distlift.languages.python import PythonProjectPlugin
    from distlift.vcs.git import GitBackendBuiltinPlugin

    return [
        GitBackendBuiltinPlugin(),
        PythonProjectPlugin(),
        JavaScriptProjectPlugin(),
    ]
