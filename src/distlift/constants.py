"""Default paths, templates, and environment-related constants."""

from pathlib import Path

ENV_PREFIX = "DISTLIFT_"

# ``DISTLIFT_HOOKS_<SUFFIX>`` appends hook specs after merged TOML (see
# loader). Suffix is SCREAMING_SNAKE of the event key (``tag_pushed`` ->
# ``TAG_PUSHED``).
HOOK_ENV_KEY_SUFFIXES: dict[str, str] = {
    "tag_pushed": "TAG_PUSHED",
    "tag_push_failed": "TAG_PUSH_FAILED",
    "release_failed": "RELEASE_FAILED",
    "build_succeeded": "BUILD_SUCCEEDED",
    "build_failed": "BUILD_FAILED",
    "publish_succeeded": "PUBLISH_SUCCEEDED",
    "publish_failed": "PUBLISH_FAILED",
}

DEFAULT_REMOTE = "origin"
DEFAULT_VERSION = "0.1.0"
DEFAULT_DEPLOY_TAG_PREFIX = "deploy"
DEFAULT_TAG_TEMPLATE = "v{version}"
DEFAULT_MONOREPO_TAG_TEMPLATE = "v{version}-{package}"

PLUGIN_ENTRY_POINT_GROUP = "distlift.plugins"

DEFAULT_LOCAL_CONFIG_FILENAMES = [
    "distlift.toml",
    ".distlift.toml",
]

PYPROJECT_TOOL_KEY = "distlift"

DEFAULT_USER_CONFIG_PATHS: list[Path] = []
DEFAULT_SYSTEM_CONFIG_PATHS: list[Path] = []


def _build_user_config_paths() -> list[Path]:
    """Return default user-level distlift config paths for this OS.

    Args:
        None

    Returns:
        Paths under the OS-specific user config location, or an empty list when
        the location cannot be determined (e.g. missing APPDATA on Windows).
    """
    import os
    import sys

    # Windows: prefer %APPDATA% when present
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            return [Path(appdata) / "distlift" / "config.toml"]
        return []

    # POSIX-style: XDG-style path under the user home directory
    home = Path.home()
    return [home / ".config" / "distlift" / "config.toml"]


def _build_system_config_paths() -> list[Path]:
    """Return default system-level distlift config paths for this OS.

    Args:
        None

    Returns:
        Paths under the OS-wide config location, or a POSIX ``/etc`` fallback
        when not on Windows.
    """
    import os
    import sys

    # Windows: prefer %ProgramData% when present
    if sys.platform == "win32":
        program_data = os.environ.get("ProgramData", "")
        if program_data:
            return [Path(program_data) / "distlift" / "config.toml"]
        return []

    return [Path("/etc/distlift/config.toml")]


DEFAULT_USER_CONFIG_PATHS = _build_user_config_paths()
DEFAULT_SYSTEM_CONFIG_PATHS = _build_system_config_paths()
