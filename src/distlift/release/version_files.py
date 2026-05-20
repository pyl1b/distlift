"""Helpers for resolving VersionFileConfig into ResolvedVersionFile objects."""

from __future__ import annotations

from pathlib import Path

from distlift.config.models import VersionFileConfig, VersionSource
from distlift.errors import ConfigurationError
from distlift.manifests.handler import (
    ManifestHandler,
    get_handler,
    kind_for_language,
)
from distlift.release.models import ResolvedVersionFile


def resolve_version_files(
    configs: list[VersionFileConfig],
    root: Path,
) -> list[ResolvedVersionFile]:
    """Resolve a list of ``VersionFileConfig`` entries to absolute paths.

    For each entry the kind is derived from ``kind`` directly, or from
    ``language`` via :func:`kind_for_language`.  The path is resolved
    relative to ``root`` when not absolute.

    Args:
        configs: Version file config entries from TOML.
        root: Package root used to resolve relative paths.
    """
    result: list[ResolvedVersionFile] = []

    for cfg in configs:
        kind = _resolve_kind(cfg)
        handler = get_handler(kind)
        path = _resolve_path(cfg, root, handler)

        result.append(
            ResolvedVersionFile(
                path=path,
                kind=kind,
                primary=cfg.primary,
                update=cfg.update,
            )
        )

    return result


def _resolve_kind(cfg: VersionFileConfig) -> str:
    """Return the manifest kind string for a version file config entry.

    Args:
        cfg: Version file config entry.
    """
    if cfg.kind:
        return cfg.kind

    if cfg.language is not None:
        derived = kind_for_language(str(cfg.language))
        if derived:
            return derived
        raise ConfigurationError(
            f"version_files entry with language={cfg.language!r} has no"
            " known manifest kind; set 'kind' explicitly"
        )

    raise ConfigurationError(
        "version_files entry must specify either 'kind' or 'language'"
    )


def _resolve_path(
    cfg: VersionFileConfig,
    root: Path,
    handler: ManifestHandler | None,
) -> Path:
    """Return the absolute manifest path for a version file config entry.

    Args:
        cfg: Version file config entry.
        root: Package root used to resolve relative paths.
        handler: Optional handler used for auto-detection when path is None.
    """
    if cfg.path:
        p = Path(cfg.path)
        return p if p.is_absolute() else root / p

    if handler is not None:
        detected = handler.detect(root)
        if detected is not None:
            return detected

    kind = cfg.kind or (
        kind_for_language(str(cfg.language)) if cfg.language else None
    )
    raise ConfigurationError(
        f"version_files entry with kind={kind!r} has no 'path' and"
        f" could not detect the manifest under {root}"
    )


def validate_version_files(
    files: list[ResolvedVersionFile],
    version_source: VersionSource,
    unit_name: str,
) -> None:
    """Raise ConfigurationError when the version file list is invalid.

    Rules:
    - If ``version_source`` is MANIFEST and files are present, exactly one
      must be marked ``primary``.
    - If ``version_source`` is MANIFEST and files are present but none is
      primary, raise with a clear message.

    Args:
        files: Resolved version files for the release unit.
        version_source: Whether versions come from manifest or tags.
        unit_name: Human-readable unit label used in error messages.
    """
    if not files:
        return

    primaries = [f for f in files if f.primary]

    if version_source == VersionSource.MANIFEST and not primaries:
        raise ConfigurationError(
            f"Release unit {unit_name!r} has version_source='manifest' and"
            " multiple version_files but none is marked primary=true."
            " Mark exactly one file as primary."
        )

    if len(primaries) > 1:
        paths = ", ".join(str(f.path) for f in primaries)
        raise ConfigurationError(
            f"Release unit {unit_name!r} has {len(primaries)} primary"
            f" version files ({paths}); exactly one is allowed."
        )


def primary_version_file(
    files: list[ResolvedVersionFile],
) -> ResolvedVersionFile | None:
    """Return the primary version file, or ``None`` when the list is empty.

    Args:
        files: Resolved version files for the release unit.
    """
    for f in files:
        if f.primary:
            return f
    return files[0] if files else None
