"""Tests for semantic validation of resolved distlift configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from distlift.config.models import (
    ChangelogConfig,
    Language,
    ManagedPackageConfig,
    MonorepoConfig,
    ReleaseMode,
    ResolvedConfig,
    VersionFormat,
)
from distlift.config.validators import validate_resolved_config
from distlift.errors import ConfigurationError

if TYPE_CHECKING:
    from typing import Any


def _base_config(**kwargs: Any) -> ResolvedConfig:
    """Build a valid resolved config with optional field overrides.

    Args:
        kwargs: ResolvedConfig field values that replace the defaults.
    """

    # Start from a minimal valid simple-mode configuration.
    defaults = dict(
        language=Language.PYTHON,
        mode=ReleaseMode.SIMPLE,
        default_version="0.1.0",
        version_format=VersionFormat.MAJOR_MINOR_PATCH,
        remotes=["origin"],
        tag_template="v{version}",
    )

    # Apply caller-provided overrides before constructing the config.
    defaults.update(kwargs)
    return ResolvedConfig(**defaults)


class TestValidateResolvedConfig:
    """Tests for resolved configuration validation rules."""

    def test_valid_config_passes(self) -> None:
        """Accept a minimal valid resolved configuration."""

        # Validate the canonical base config.
        validate_resolved_config(_base_config())

    def test_bad_remote_raises(self) -> None:
        """Reject remote names containing invalid characters."""

        # Validate a config with a syntactically invalid remote name.
        with pytest.raises(ConfigurationError):
            validate_resolved_config(_base_config(remotes=[" bad remote!"]))

    def test_tag_template_without_version_raises(self) -> None:
        """Reject tag templates that omit the version placeholder."""

        # Validate a config whose tag template cannot include versions.
        with pytest.raises(ConfigurationError):
            validate_resolved_config(
                _base_config(tag_template="release-{pkg}")
            )

    def test_monorepo_without_packages_raises(self) -> None:
        """Reject enabled monorepo mode without configured packages."""

        # Build a monorepo config with no managed package declarations.
        config = _base_config(
            mode=ReleaseMode.MONOREPO,
            monorepo=MonorepoConfig(enabled=True, packages=[]),
        )

        # Validate that empty monorepo package lists are not accepted.
        with pytest.raises(ConfigurationError):
            validate_resolved_config(config)

    def test_monorepo_duplicate_names_raises(self) -> None:
        """Reject monorepo package declarations with duplicate names."""

        # Build a monorepo config with the same package listed twice.
        pkg = ManagedPackageConfig(name="a", path="packages/a")
        config = _base_config(
            mode=ReleaseMode.MONOREPO,
            monorepo=MonorepoConfig(enabled=True, packages=[pkg, pkg]),
        )

        # Validate that duplicate package names are rejected.
        with pytest.raises(ConfigurationError):
            validate_resolved_config(config)

    def test_changelog_compare_template_requires_both_refs(self) -> None:
        """Reject malformed changelog compare URL templates."""

        bad = ChangelogConfig(
            compare_url_template="https://example.com/{prev}",
        )
        config = _base_config(changelog=bad)

        with pytest.raises(ConfigurationError):
            validate_resolved_config(config)

    def test_changelog_commit_mapping_must_be_known_sections(self) -> None:
        """Reject unknown Keep a Changelog section titles."""

        bad = ChangelogConfig(commit_mapping={"feat": "Nope"})
        config = _base_config(changelog=bad)

        with pytest.raises(ConfigurationError):
            validate_resolved_config(config)
