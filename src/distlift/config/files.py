"""Locate, create, and open distlift config files on disk.

This module supports the ``distlift config init-user``,
``distlift config init-system``, ``distlift config init-repo``,
``distlift config edit-user``, ``distlift config edit-system``, and
``distlift config edit-repo`` commands. It manages the files on disk and,
for the ``edit-*`` commands, resolves the merged ``editor`` setting so the
configured editor (if any) is honored as a fallback. User and system
``edit-*`` commands load global layers only; ``edit-repo`` includes the
repository root when resolving ``editor``.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from distlift.config.discovery import discover_local_config_paths
from distlift.config.loader import load_config_layers
from distlift.config.merger import merge_config_layers
from distlift.constants import (
    DEFAULT_LOCAL_CONFIG_FILENAMES,
    DEFAULT_SYSTEM_CONFIG_PATHS,
    DEFAULT_USER_CONFIG_PATHS,
)
from distlift.editor import launch_editor_blocking
from distlift.errors import ConfigurationError
from distlift.logging_utils import get_logger

log = get_logger(__name__)


class ConfigScope(StrEnum):
    """Which preset configuration location a command targets.

    Attributes:
        USER: Per-user configuration (``%APPDATA%`` on Windows,
            ``~/.config`` on POSIX).
        SYSTEM: Machine-wide configuration (``%ProgramData%`` on Windows,
            ``/etc`` on POSIX).
    """

    USER = "user"
    SYSTEM = "system"


STUB_CONFIG_CONTENT: str = """\
# distlift configuration
#
# All keys are optional; defaults shown in comments. Uncomment and edit
# the ones you want to override.
#
# Precedence (highest first):
#   1. CLI flags
#   2. DISTLIFT_* environment variables
#   3. Local repo config (distlift.toml, .distlift.toml, [tool.distlift])
#   4. User config (this file, when in the user location)
#   5. System config (this file, when in the system location)
#   6. Built-in defaults
#
# Release-related keys (language, editor, remotes, …) may appear at the
# top level below, or only under `[release]`. If you add `[release]`, put
# those fields inside it—top-level duplicates are ignored by the parser.

# language = "python"                 # python | javascript
# mode = "simple"                     # simple | monorepo
# default_version = "0.1.0"
# version_format = "major-minor-patch"  # major | major-minor | (default)
# tag_template = "v{version}"
# version_source = "manifest"         # manifest | tag
# manifest_path = "pyproject.toml"
# remotes = ["origin"]

# Optional: default external editor for this machine (user or system file).
# Used when GIT_EDITOR, VISUAL, and EDITOR are all unset—for example
# ``distlift config edit-*`` and changelog entry editing. Same value can be
# set via DISTLIFT_EDITOR instead of this file.
# editor = "code --wait"

# [changelog]
# enabled = true
# path = "CHANGELOG.md"
# title = "Changelog"
# prompt_editor = true
# compare_url_template = ""           # auto-derived from origin when empty

# [plugins]
# enable_environment = true
# enable_builtin = true
# allow_override = true
# paths = []
# directories = []
"""


def _default_path_for_scope(scope: ConfigScope) -> Path:
    """Return the canonical config path for the given scope on this OS.

    Args:
        scope: Whether to look up the user-level or system-level location.

    Raises:
        ConfigurationError: When the OS-specific environment does not expose
            a default location for this scope (e.g. ``%APPDATA%`` unset).
    """
    candidates = (
        DEFAULT_USER_CONFIG_PATHS
        if scope is ConfigScope.USER
        else DEFAULT_SYSTEM_CONFIG_PATHS
    )

    if not candidates:
        # Empty list means the OS-specific lookup couldn't determine a path
        env_hint = "APPDATA" if scope is ConfigScope.USER else "ProgramData"

        raise ConfigurationError(
            f"Cannot determine the default {scope.value} configuration "
            f"location on this system (missing %{env_hint}% on Windows?)."
        )

    return candidates[0]


def get_user_config_path() -> Path:
    """Return the canonical user-level distlift config file path.

    Raises:
        ConfigurationError: When the user config location cannot be
            determined on this platform.
    """
    return _default_path_for_scope(ConfigScope.USER)


def get_system_config_path() -> Path:
    """Return the canonical system-level distlift config file path.

    Raises:
        ConfigurationError: When the system config location cannot be
            determined on this platform.
    """
    return _default_path_for_scope(ConfigScope.SYSTEM)


def get_config_path(scope: ConfigScope) -> Path:
    """Return the canonical config file path for ``scope``.

    Args:
        scope: Which preset location (user or system) to resolve.

    Raises:
        ConfigurationError: When the location cannot be determined.
    """
    return _default_path_for_scope(scope)


def create_config_file(
    scope: ConfigScope,
    *,
    force: bool = False,
) -> tuple[Path, bool]:
    """Create the user or system config file with a commented stub.

    Args:
        scope: Whether to target the user-level or system-level location.
        force: When True, overwrite an existing file with the stub. When
            False, leave the existing file untouched.

    Returns:
        A tuple ``(path, created)`` where ``created`` is ``True`` when a
        new file (or an overwrite via ``force``) was written, and ``False``
        when the file already existed and was preserved.

    Raises:
        ConfigurationError: When the target location cannot be determined.
        OSError: When the file or its parent directories cannot be written
            (e.g. permission denied for the system path).
    """
    path = get_config_path(scope)

    # Skip the write when the file already exists and the caller did not
    # ask for an overwrite, so we never clobber an edited config
    if path.exists() and not force:
        log.debug(
            "Config file already exists for scope %s at %s; not overwriting",
            scope.value,
            path,
        )

        return path, False

    # Ensure the parent directory exists before writing the stub
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(STUB_CONFIG_CONTENT, encoding="utf-8", newline="\n")

    log.info(
        "Wrote %s config stub to %s",
        scope.value,
        path,
    )

    return path, True


def get_repo_config_init_path(repo_root: Path) -> Path:
    """Return the path where ``init-repo`` writes a new stub file.

    Standalone repo config is ``distlift.toml`` or ``.distlift.toml``; new
    stubs are always created as ``distlift.toml`` next to ``repo_root``.

    Args:
        repo_root: Repository root directory (absolute or relative).
    """
    return repo_root.resolve() / DEFAULT_LOCAL_CONFIG_FILENAMES[0]


def _resolve_existing_repo_standalone_config_path(
    repo_root: Path,
) -> Path | None:
    """Return the standalone local config file with highest merge precedence.

    ``load_config_layers`` merges ``distlift.toml`` before ``.distlift.toml``,
    so when both exist the latter wins and is the file users usually want to
    open for editing.

    Args:
        repo_root: Repository root directory (absolute or relative).

    Returns:
        The path to open, or ``None`` when neither standalone file exists.
    """
    paths = discover_local_config_paths(repo_root.resolve())

    if not paths:
        return None

    return paths[-1]


def create_repo_config_file(
    repo_root: Path,
    *,
    force: bool = False,
) -> tuple[Path, bool]:
    """Create ``distlift.toml`` under the repository root with a commented stub.

    Args:
        repo_root: Repository root directory (absolute or relative).
        force: When True, overwrite an existing ``distlift.toml``. When False,
            leave an existing ``distlift.toml`` untouched.

    Returns:
        A tuple ``(path, created)`` where ``path`` is ``distlift.toml`` under
        ``repo_root``, and ``created`` is ``True`` when a new file (or an
        overwrite via ``force``) was written.

    Raises:
        OSError: When the file or its parent directories cannot be written.
    """
    path = get_repo_config_init_path(repo_root)

    # Skip the write when the file already exists and the caller did not
    # ask for an overwrite, so we never clobber an edited config
    if path.exists() and not force:
        log.debug(
            "Repo config file already exists at %s; not overwriting",
            path,
        )

        return path, False

    # Ensure the parent directory exists before writing the stub
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(STUB_CONFIG_CONTENT, encoding="utf-8", newline="\n")

    log.info("Wrote repo config stub to %s", path)

    return path, True


def _resolve_repo_editor_command(repo_root: Path) -> str | None:
    """Return the merged ``editor`` setting including repository TOML layers.

    Args:
        repo_root: Absolute repository root used when loading config layers.
    """
    try:
        layers = load_config_layers(repo_root=repo_root)
        resolved = merge_config_layers(layers)
    except ConfigurationError:
        log.debug(
            "Could not load config layers for repo editor resolution at %s",
            repo_root,
            exc_info=True,
        )

        return None

    return resolved.editor


def open_repo_config_file_in_editor(
    repo_root: Path,
    *,
    create_if_missing: bool = True,
) -> tuple[Path, int]:
    """Open the repository standalone config file in the user's editor.

    When ``distlift.toml`` and/or ``.distlift.toml`` exist, the file that wins
    in merge order (``.distlift.toml`` when both are present) is opened. When
    neither exists, ``distlift.toml`` is created with the default stub unless
    ``create_if_missing`` is False.

    Args:
        repo_root: Repository root directory (absolute or relative).
        create_if_missing: When True (default), seed ``distlift.toml`` before
            launching the editor when no standalone file exists. When False,
            raise ``ConfigurationError`` instead.

    Returns:
        A tuple ``(path, exit_code)`` with the path that was opened and the
        editor process exit code.

    Raises:
        ConfigurationError: When no editor environment variable or config
            ``editor`` is set, or when no standalone file exists and
            ``create_if_missing`` is False.
        OSError: When the file or its parent directories cannot be created.
    """
    root = repo_root.resolve()
    existing = _resolve_existing_repo_standalone_config_path(root)

    if existing is not None:
        path = existing
    else:
        path = get_repo_config_init_path(root)

        if not path.exists():
            if not create_if_missing:
                raise ConfigurationError(
                    f"Repo config file does not exist under {root}. Run "
                    "'distlift config init-repo' first."
                )

            # Seed distlift.toml so the editor opens a meaningful file
            create_repo_config_file(root, force=False)

    # Honor editor from merged config (system, user, pyproject, local, env)
    config_editor = _resolve_repo_editor_command(root)

    exit_code = launch_editor_blocking(path, config_editor=config_editor)

    return path, exit_code


def _resolve_global_editor_command() -> str | None:
    """Return the merged ``editor`` setting from system + user + env layers.

    The ``config edit-*`` commands intentionally operate without a repo
    root, so this only loads the global layers (system file, user file,
    ``DISTLIFT_EDITOR``). When none of them specify ``editor``, ``None`` is
    returned and the call site relies solely on the environment editor
    variables.
    """
    try:
        layers = load_config_layers(repo_root=None)
        resolved = merge_config_layers(layers)
    except ConfigurationError:
        log.debug(
            "Could not load global config layers for editor resolution",
            exc_info=True,
        )
        return None

    return resolved.editor


def open_config_file_in_editor(
    scope: ConfigScope,
    *,
    create_if_missing: bool = True,
) -> tuple[Path, int]:
    """Open the user or system config file in the user's editor.

    Args:
        scope: Whether to target the user-level or system-level location.
        create_if_missing: When True (default), seed a stub config file
            before launching the editor if no file exists yet. When False,
            raise ``ConfigurationError`` instead.

    Returns:
        A tuple ``(path, exit_code)`` with the path that was opened and the
        editor process exit code.

    Raises:
        ConfigurationError: When the target location cannot be determined,
            when no editor environment variable or config ``editor`` is
            set, or when the file is missing and ``create_if_missing`` is
            False.
        OSError: When the file or its parent directories cannot be created.
    """
    path = get_config_path(scope)

    if not path.exists():
        if not create_if_missing:
            raise ConfigurationError(
                f"{scope.value.capitalize()} config file does not exist at "
                f"{path}. Run 'distlift config init-{scope.value}' first."
            )

        # Seed a stub so the editor opens a meaningful file the first time
        create_config_file(scope, force=False)

    # Read merged ``editor`` from system + user + env so the configured
    # fallback is honored when no editor env var is set
    config_editor = _resolve_global_editor_command()

    exit_code = launch_editor_blocking(path, config_editor=config_editor)

    return path, exit_code
