"""Scaffolding helpers for distlift plugin projects."""

from __future__ import annotations

import re
from pathlib import Path

import attrs

from distlift.config.models import (
    DependencyUpdateRule,
    ExternalMonorepoDependencyUpdateConfig,
)
from distlift.errors import ConfigurationError


@attrs.define
class DependencyUpdaterTemplateOptions:
    """Inputs for creating a dependency updater plugin template.

    Attributes:
        name: Python package and plugin name.
        output_dir: Directory where the plugin project is written.
        rules: Initial dependency update rules.
        external_monorepos: Initial external monorepo targets.
        force: Whether existing files may be overwritten.
        python_version_template: Default Python version specifier template.
        javascript_version_template: Default JavaScript version template.
    """

    name: str
    output_dir: Path
    rules: list[DependencyUpdateRule]
    external_monorepos: list[ExternalMonorepoDependencyUpdateConfig]
    force: bool = False
    python_version_template: str = ">={version}"
    javascript_version_template: str = "^{version}"


def create_dependency_updater_plugin(
    options: DependencyUpdaterTemplateOptions,
) -> list[Path]:
    """Create a pip-installable dependency updater plugin project.

    Args:
        options: Template generation inputs.

    Returns:
        Paths of files written under ``options.output_dir``.
    """
    output = options.output_dir.resolve()
    normalized = _normalize_package_name(options.name)
    pkg_dir = output / normalized
    written: list[Path] = []

    if output.exists() and not options.force and any(output.iterdir()):
        raise ConfigurationError(
            f"Output directory {output} is not empty; use --force to overwrite"
        )

    pkg_dir.mkdir(parents=True, exist_ok=True)

    files = _template_files(options, normalized)

    for rel_path, content in files.items():
        dest = output / rel_path

        if dest.exists() and not options.force:
            raise ConfigurationError(
                f"File already exists: {dest}; use --force to overwrite"
            )

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        written.append(dest)

    return written


def _normalize_package_name(name: str) -> str:
    """Convert a plugin name to a valid Python package directory name.

    Args:
        name: User-supplied plugin name.
    """
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip()).strip("_").lower()

    if not slug or slug[0].isdigit():
        raise ConfigurationError(
            f"Invalid plugin name {name!r}; use letters, digits, or hyphens"
        )

    return slug


def _template_files(
    options: DependencyUpdaterTemplateOptions,
    normalized: str,
) -> dict[str, str]:
    """Build relative path to file content mappings for the template.

    Args:
        options: Template generation inputs.
        normalized: Normalized Python package directory name.
    """
    project_name = (
        f"distlift-{normalized.replace('_', '-')}-dependency-updater"
    )
    plugin_name = normalized.replace("_", "-")
    dep_toml = _dependency_updater_toml(options)

    pyproject = f"""[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "{project_name}"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["distlift"]

[project.entry-points."distlift.plugins"]
{normalized} = "{normalized}:get_plugin"

[tool.hatch.build.targets.wheel]
packages = ["{normalized}"]
"""

    readme = f"""# {plugin_name} dependency updater

Distlift plugin that updates dependent package manifests when packages are
released.

## Install

```bash
python -m pip install -e .
```

Or load from a directory without installing:

```toml
[plugins]
directories = ["{options.output_dir.name}"]
```

## Configuration

Edit ``dependency-updater.toml`` next to ``plugin.py``.
"""

    plugin_py = f'''from __future__ import annotations

from pathlib import Path

from distlift.dependencies.configured_plugin import (
    ConfiguredDependencyUpdaterPlugin,
)


def get_plugin() -> ConfiguredDependencyUpdaterPlugin:
    """Return the configured dependency updater plugin."""
    return ConfiguredDependencyUpdaterPlugin.from_file(
        name="{plugin_name}",
        version="0.1.0",
        config_path=Path(__file__).with_name("dependency-updater.toml"),
    )
'''

    init_py = '''"""Dependency updater plugin package."""

from .plugin import get_plugin

__all__ = ["get_plugin"]
'''

    return {
        "pyproject.toml": pyproject,
        "README.md": readme,
        f"{normalized}/__init__.py": init_py,
        f"{normalized}/plugin.py": plugin_py,
        f"{normalized}/dependency-updater.toml": dep_toml,
    }


def _dependency_updater_toml(
    options: DependencyUpdaterTemplateOptions,
) -> str:
    """Build the packaged dependency-updater.toml content.

    Args:
        options: Template generation inputs.
    """
    return _rules_toml(options)


def _rules_toml(options: DependencyUpdaterTemplateOptions) -> str:
    """Serialize dependency update rules into TOML text.

    Args:
        options: Template generation inputs.
    """
    lines = [
        "[dependency_updates]",
        "enabled = true",
        f'python_version_template = "{options.python_version_template}"',
        (
            f"javascript_version_template = "
            f'"{options.javascript_version_template}"'
        ),
        "",
    ]

    for rule in options.rules:
        lines.append("[[dependency_updates.rules]]")
        lines.append(f'package = "{rule.package}"')

        if rule.dependency_name:
            lines.append(f'dependency_name = "{rule.dependency_name}"')

        projects = ", ".join(f'"{p}"' for p in rule.projects)
        lines.append(f"projects = [{projects}]")

        if rule.version_template:
            lines.append(f'version_template = "{rule.version_template}"')

        lines.append("")

    for ext in options.external_monorepos:
        lines.append("[[dependency_updates.external_monorepos]]")
        lines.append(f'path = "{ext.path}"')

        if ext.config_paths:
            paths = ", ".join(f'"{p}"' for p in ext.config_paths)
            lines.append(f"config_paths = [{paths}]")

        projects = ", ".join(f'"{p}"' for p in ext.projects)
        lines.append(f"projects = [{projects}]")
        lines.append("")

    return "\n".join(lines)
