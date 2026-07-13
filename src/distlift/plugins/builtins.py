"""Construct the default built-in ``DistliftPlugin`` list."""

from __future__ import annotations

from distlift.plugins.base import DistliftPlugin


def build_builtin_plugins() -> list[DistliftPlugin]:
    """Return all built-in plugin instances in default registration order."""
    from distlift.changelog.plugin import KeepAChangelogBuiltinPlugin
    from distlift.languages.javascript import JavaScriptProjectPlugin
    from distlift.languages.python import PythonProjectPlugin
    from distlift.package_managers.npm import NpmPackageManagerPlugin
    from distlift.package_managers.pip import PipPackageManagerPlugin
    from distlift.package_managers.pnpm import PnpmPackageManagerPlugin
    from distlift.package_managers.yarn import YarnPackageManagerPlugin
    from distlift.vcs.git import GitBackendBuiltinPlugin

    return [
        GitBackendBuiltinPlugin(),
        KeepAChangelogBuiltinPlugin(),
        PythonProjectPlugin(),
        JavaScriptProjectPlugin(),
        PipPackageManagerPlugin(),
        NpmPackageManagerPlugin(),
        PnpmPackageManagerPlugin(),
        YarnPackageManagerPlugin(),
    ]
