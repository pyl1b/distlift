from pathlib import Path

ENV_PREFIX = "DISTLIFT_"

DEFAULT_REMOTE = "origin"
DEFAULT_VERSION = "0.1.0"
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
    import os
    import sys

    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            return [Path(appdata) / "distlift" / "config.toml"]
        return []
    home = Path.home()
    return [home / ".config" / "distlift" / "config.toml"]


def _build_system_config_paths() -> list[Path]:
    import os
    import sys

    if sys.platform == "win32":
        program_data = os.environ.get("ProgramData", "")
        if program_data:
            return [Path(program_data) / "distlift" / "config.toml"]
        return []
    return [Path("/etc/distlift/config.toml")]


DEFAULT_USER_CONFIG_PATHS = _build_user_config_paths()
DEFAULT_SYSTEM_CONFIG_PATHS = _build_system_config_paths()
