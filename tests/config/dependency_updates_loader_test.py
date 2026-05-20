"""Tests for dependency_updates configuration loading."""

from distlift.config.loader import dependency_updates_from_mapping


class TestDependencyUpdatesLoader:
    """Tests for parsing [dependency_updates] tables."""

    def test_parses_rules_and_templates(self) -> None:
        """Load rules, templates, and enablement from a mapping."""
        data = {
            "enabled": True,
            "python_version_template": "=={version}",
            "rules": [
                {
                    "package": "a",
                    "projects": ["b", "c"],
                    "version_template": ">={version}",
                },
            ],
        }

        config = dependency_updates_from_mapping(data)

        assert config.enabled is True
        assert config.python_version_template == "=={version}"
        assert len(config.rules) == 1
        assert config.rules[0].package == "a"
        assert config.rules[0].projects == ["b", "c"]
