import pytest

from distlift.config.models import (
    Language,
    ManagedPackageConfig,
    MonorepoConfig,
    ReleaseMode,
    ResolvedConfig,
    VersionFormat,
)
from distlift.config.validators import validate_resolved_config
from distlift.errors import ConfigurationError


def _base_config(**kwargs) -> ResolvedConfig:
    defaults = dict(
        language=Language.PYTHON,
        mode=ReleaseMode.SIMPLE,
        default_version="0.1.0",
        version_format=VersionFormat.MAJOR_MINOR_PATCH,
        remotes=["origin"],
        tag_template="v{version}",
    )
    defaults.update(kwargs)
    return ResolvedConfig(**defaults)


class TestValidateResolvedConfig:
    def test_valid_config_passes(self):
        validate_resolved_config(_base_config())

    def test_bad_remote_raises(self):
        with pytest.raises(ConfigurationError):
            validate_resolved_config(_base_config(remotes=[" bad remote!"]))

    def test_tag_template_without_version_raises(self):
        with pytest.raises(ConfigurationError):
            validate_resolved_config(_base_config(tag_template="release-{pkg}"))

    def test_monorepo_without_packages_raises(self):
        config = _base_config(
            mode=ReleaseMode.MONOREPO,
            monorepo=MonorepoConfig(enabled=True, packages=[]),
        )
        with pytest.raises(ConfigurationError):
            validate_resolved_config(config)

    def test_monorepo_duplicate_names_raises(self):
        pkg = ManagedPackageConfig(name="a", path="packages/a")
        config = _base_config(
            mode=ReleaseMode.MONOREPO,
            monorepo=MonorepoConfig(enabled=True, packages=[pkg, pkg]),
        )
        with pytest.raises(ConfigurationError):
            validate_resolved_config(config)
