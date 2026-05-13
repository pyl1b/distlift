from __future__ import annotations

from pathlib import Path

from distlift.config.models import Language, ResolvedConfig, VersionSource
from distlift.errors import ManifestUpdateError
from distlift.languages.base import ProjectAdapter
from distlift.manifests.package_json_file import (
    get_package_version,
    read_package_json,
    set_package_version,
)
from distlift.plugins.base import LanguagePlugin
from distlift.plugins.registry import PluginRegistry


class JavaScriptProjectAdapter(ProjectAdapter):
    def detect_project(self, root: Path) -> bool:
        return (root / "package.json").exists()

    def load_release_target(
        self, root: Path, config: ResolvedConfig
    ) -> "ReleaseTarget":
        from distlift.release.models import ReleaseTarget

        manifest = config.manifest_path or (root / "package.json")
        return ReleaseTarget(
            language=Language.JAVASCRIPT,
            root=root,
            manifest_path=manifest,
            version_source=config.version_source,
        )

    def is_dynamic_version(self, target: "ReleaseTarget") -> bool:
        return target.version_source == VersionSource.TAG

    def read_manifest_version(self, target: "ReleaseTarget") -> str | None:
        try:
            data = read_package_json(target.manifest_path)
            return get_package_version(data)
        except ManifestUpdateError:
            return None

    def update_manifest_version(self, target: "ReleaseTarget", version: str) -> None:
        set_package_version(target.manifest_path, version)


class JavaScriptProjectPlugin(LanguagePlugin):
    def get_name(self) -> str:
        return "builtin-javascript"

    def get_version(self) -> str:
        return "1.0.0"

    def get_language(self) -> str:
        return Language.JAVASCRIPT.value

    def register(self, registry: PluginRegistry) -> None:
        registry.register_language_plugin(self, source="builtin")
