"""Re-exports for manifest helpers used by language adapters."""

from distlift.manifests.package_json_file import (
    get_package_version,
    read_package_json,
    set_package_version,
)
from distlift.manifests.pyproject_file import (
    get_project_version,
    project_uses_dynamic_version,
    read_pyproject,
    set_project_version,
)

__all__ = [
    "read_pyproject",
    "project_uses_dynamic_version",
    "get_project_version",
    "set_project_version",
    "read_package_json",
    "get_package_version",
    "set_package_version",
]
