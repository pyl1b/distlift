"""Construct the default built-in ``DistliftPlugin`` list."""

from __future__ import annotations

from distlift.plugins.base import DistliftPlugin


def build_builtin_plugins() -> list[DistliftPlugin]:
    """Return all built-in plugin instances in default registration order."""
    from distlift.changelog.plugin import KeepAChangelogBuiltinPlugin
    from distlift.languages.javascript import JavaScriptProjectPlugin
    from distlift.languages.python import PythonProjectPlugin
    from distlift.vcs.git import GitBackendBuiltinPlugin

    return [
        GitBackendBuiltinPlugin(),
        KeepAChangelogBuiltinPlugin(),
        PythonProjectPlugin(),
        JavaScriptProjectPlugin(),
    ]
