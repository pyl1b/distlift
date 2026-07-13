"""Shared helpers for built-in package manager plugins."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from distlift.config.models import Language, ResolvedConfig
from distlift.dependencies.javascript import _WORKSPACE_PREFIXES
from distlift.dependencies.models import DependencyProject
from distlift.dependencies.upgrade_models import (
    DependencySelection,
    PluginCommandResult,
)
from distlift.errors import ManifestUpdateError
from distlift.logging_utils import get_logger
from distlift.manifests.package_json_file import read_package_json
from distlift.plugins.base import PackageManagerPlugin

log = get_logger(__name__)


def run_command(
    cmd: list[str],
    *,
    cwd: Path,
    dry_run: bool,
    timeout_seconds: int,
    mutating: bool,
) -> PluginCommandResult:
    """Run or preview one package-manager subprocess.

    Args:
        cmd: argv to execute.
        cwd: Working directory for the command.
        dry_run: When True, skip mutating commands.
        timeout_seconds: Subprocess timeout in seconds.
        mutating: Whether the command may change project files.
    """
    if dry_run and mutating:
        log.log(1, "Would run %s in %s", " ".join(cmd), cwd)
        return PluginCommandResult(command=cmd, returncode=0)

    log.log(1, "Running %s in %s", " ".join(cmd), cwd)

    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_seconds,
    )

    return PluginCommandResult(
        command=cmd,
        returncode=result.returncode,
        stdout=result.stdout or "",
        stderr=result.stderr or "",
    )


def python_pip_requirement(package_name: str, specifier: str) -> str:
    """Build one pip install requirement string.

    Args:
        package_name: Declared distribution name.
        specifier: Version specifier such as ``>=1.2.0``.
    """
    if specifier.startswith(("==", ">=", "<=", ">", "<", "!=", "~=")):
        return f"{package_name}{specifier}"

    return f"{package_name}{specifier}"


def verify_installed_package_versions(
    installed_versions: dict[str, str],
    selections: list[DependencySelection],
) -> list[str]:
    """Return errors when installed versions are below selected targets.

    Args:
        installed_versions: Versions currently installed in the environment.
        selections: Applied selections with target versions.
    """
    from packaging.version import Version

    errors: list[str] = []

    for selection in selections:
        if selection.target_version is None:
            continue

        name = selection.dependency.name
        installed = installed_versions.get(name)

        if not installed:
            errors.append(f"{name} not installed in environment")
            continue

        try:
            if Version(installed) < Version(selection.target_version):
                errors.append(
                    f"{name} installed as {installed}, expected "
                    f">= {selection.target_version}"
                )
        except Exception as exc:
            log.log(
                1,
                "Could not compare installed version for %s: %s",
                name,
                exc,
                exc_info=True,
            )
            errors.append(
                f"{name} installed version {installed!r} could not be verified"
            )

    return errors


def read_npm_lock_versions(lock_path: Path) -> dict[str, str]:
    """Read direct dependency versions from ``package-lock.json``.

    Args:
        lock_path: Path to the npm lock file.
    """
    if not lock_path.is_file():
        return {}

    try:
        data = json.loads(lock_path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.log(
            1,
            "Could not parse lock file %s: %s",
            lock_path,
            exc,
            exc_info=True,
        )
        return {}

    versions: dict[str, str] = {}
    packages = data.get("packages", {})

    if isinstance(packages, dict):
        for key, entry in packages.items():
            if not isinstance(entry, dict):
                continue

            if key == "":
                continue

            name = key.removeprefix("node_modules/")
            version = entry.get("version")

            if name and version:
                versions[name] = str(version)

    dependencies = data.get("dependencies", {})

    if isinstance(dependencies, dict):
        for name, entry in dependencies.items():
            if not isinstance(entry, dict):
                continue

            version = entry.get("version")

            if version:
                versions[str(name)] = str(version)

    return versions


def package_manager_field(root: Path) -> str | None:
    """Return the ``packageManager`` field from ``package.json`` when set.

    Args:
        root: JavaScript project root directory.
    """
    manifest = root / "package.json"

    if not manifest.is_file():
        return None

    try:
        data = read_package_json(manifest)
    except ManifestUpdateError:
        return None

    value = data.get("packageManager")

    if value is None:
        return None

    return str(value).strip() or None


def manager_from_package_manager_field(value: str | None) -> str | None:
    """Map a ``packageManager`` value to a manager id.

    Args:
        value: Raw ``packageManager`` field contents.
    """
    if not value:
        return None

    lowered = value.lower()

    if lowered.startswith("npm@"):
        return "npm"

    if lowered.startswith("pnpm@"):
        return "pnpm"

    if lowered.startswith("yarn@"):
        return "yarn"

    return None


def preserve_python_specifier_style(
    constraint: str,
    target_version: str,
    config: ResolvedConfig,
) -> str:
    """Build a Python specifier preserving the original operator family.

    Args:
        constraint: Existing requirement string.
        target_version: Selected target version.
        config: Effective configuration for fallback templates.
    """
    stripped = constraint.strip()

    if stripped.startswith("=="):
        return f"=={target_version}"

    if stripped.startswith(">="):
        return f">={target_version}"

    if stripped.startswith("^"):
        return config.dependency_updates.javascript_version_template.replace(
            "{version}", target_version
        )

    return config.dependency_updates.python_version_template.replace(
        "{version}", target_version
    )


def preserve_javascript_specifier_style(
    constraint: str,
    target_version: str,
    config: ResolvedConfig,
) -> str:
    """Build a JavaScript specifier preserving range style when possible.

    Args:
        constraint: Existing specifier from package.json.
        target_version: Selected target version.
        config: Effective configuration for fallback templates.
    """
    stripped = constraint.strip()

    for prefix in _WORKSPACE_PREFIXES:
        if stripped == prefix:
            return (
                config.dependency_updates.javascript_version_template.replace(
                    "{version}", target_version
                )
            )

    if stripped.startswith("^"):
        return f"^{target_version}"

    if stripped.startswith("~"):
        return f"~{target_version}"

    if stripped.startswith(">="):
        return f">={target_version}"

    return config.dependency_updates.javascript_version_template.replace(
        "{version}", target_version
    )


class BuiltinPackageManagerPlugin(PackageManagerPlugin):
    """Common registration helpers for built-in package manager plugins.

    Attributes:
        _manager_name: Stable manager id returned by ``get_manager_name``.
        _plugin_version: Version string reported by ``get_version``.
    """

    _manager_name: str
    _plugin_version: str = "1.0.0"

    def get_name(self) -> str:
        """Return the built-in plugin name."""
        return f"builtin-package-manager-{self._manager_name}"

    def get_version(self) -> str:
        """Return the bundled plugin version string."""
        return self._plugin_version

    def get_manager_name(self) -> str:
        """Return the package manager id."""
        return self._manager_name

    def register(self, registry) -> None:
        """Register this plugin as a package manager implementation.

        Args:
            registry: Registry receiving the package manager binding.
        """
        registry.register_package_manager_plugin(self, source="builtin")

    def _project_matches_language(
        self,
        project: DependencyProject,
        language: Language,
        *,
        override_name: str | None,
    ) -> bool:
        """Return whether override or project language matches.

        Args:
            project: Candidate dependency project.
            language: Required project language.
            override_name: Optional forced manager name.
        """
        if override_name is not None:
            return override_name == self._manager_name

        return project.language == language
