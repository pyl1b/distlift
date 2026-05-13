from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from distlift.config.models import Language, ResolvedConfig, VersionSource

if TYPE_CHECKING:
    from distlift.release.models import ReleaseTarget
from distlift.errors import ManifestUpdateError
from distlift.languages.base import ProjectAdapter
from distlift.manifests.pyproject_file import (
    get_project_version,
    project_uses_dynamic_version,
    read_pyproject,
    set_project_version,
)
from distlift.plugins.base import LanguagePlugin
from distlift.plugins.registry import PluginRegistry


class PythonProjectAdapter(ProjectAdapter):
    def detect_project(self, root: Path) -> bool:
        return (root / "pyproject.toml").exists()

    def load_release_target(
        self, root: Path, config: ResolvedConfig
    ) -> ReleaseTarget:
        from distlift.release.models import (
            ReleaseTarget,  # avoid circular at runtime
        )

        manifest = config.manifest_path or (root / "pyproject.toml")
        return ReleaseTarget(
            language=Language.PYTHON,
            root=root,
            manifest_path=manifest,
            version_source=config.version_source,
        )

    def is_dynamic_version(self, target: ReleaseTarget) -> bool:
        if target.version_source == VersionSource.TAG:
            return True
        try:
            data = read_pyproject(target.manifest_path)
            return project_uses_dynamic_version(data)
        except ManifestUpdateError:
            return False

    def read_manifest_version(self, target: ReleaseTarget) -> str | None:
        try:
            data = read_pyproject(target.manifest_path)
            return get_project_version(data)
        except ManifestUpdateError:
            return None

    def update_manifest_version(
        self, target: ReleaseTarget, version: str
    ) -> None:
        set_project_version(target.manifest_path, version)


class PythonProjectPlugin(LanguagePlugin):
    def get_name(self) -> str:
        return "builtin-python"

    def get_version(self) -> str:
        return "1.0.0"

    def get_language(self) -> str:
        return Language.PYTHON.value

    def register(self, registry: PluginRegistry) -> None:
        registry.register_language_plugin(self, source="builtin")
