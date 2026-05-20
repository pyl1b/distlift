"""Tests for dependency_updates configuration validation."""

import pytest

from distlift.config.models import DependencyUpdatesConfig, ResolvedConfig
from distlift.config.validators import validate_dependency_updates_config
from distlift.errors import ConfigurationError


class TestDependencyUpdatesValidators:
    """Tests for dependency_updates validation rules."""

    def test_requires_version_placeholder(self) -> None:
        """Reject templates that omit {version}."""
        config = ResolvedConfig(
            dependency_updates=DependencyUpdatesConfig(
                python_version_template="1.0.0",
            ),
        )

        with pytest.raises(ConfigurationError):
            validate_dependency_updates_config(config)
