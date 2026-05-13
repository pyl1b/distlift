"""Tests for lifecycle hook parsing and execution."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from distlift.config.loader import (
    hooks_config_from_mapping,
    load_environment_config,
    parse_hooks_env_value,
)
from distlift.config.merger import merge_config_layers
from distlift.config.models import (
    HooksConfig,
    HookSpec,
    RawConfig,
    ResolvedConfig,
)
from distlift.config.validators import validate_hooks_config
from distlift.errors import ConfigurationError, HookExecutionError
from distlift.hooks import (
    build_hook_env,
    run_hook_specs,
    specs_for_event,
)


class TestParseHooksEnvValue:
    """Tests for ``parse_hooks_env_value``."""

    def test_newline_shell_lines(self) -> None:
        """Multiple lines become separate shell hooks."""

        specs = parse_hooks_env_value(" echo one \necho two\n")

        assert specs == [
            HookSpec(shell="echo one"),
            HookSpec(shell="echo two"),
        ]

    def test_json_string_array(self) -> None:
        """JSON list of strings becomes shell hooks."""

        raw = json.dumps(["a", "b"])
        specs = parse_hooks_env_value(raw)

        assert specs == [HookSpec(shell="a"), HookSpec(shell="b")]

    def test_json_argv_array(self) -> None:
        """JSON list of argv arrays becomes argv hooks."""

        raw = json.dumps([["py", "-c", "1"], ["x", "y"]])
        specs = parse_hooks_env_value(raw)

        assert specs == [
            HookSpec(argv=["py", "-c", "1"]),
            HookSpec(argv=["x", "y"]),
        ]


class TestLoadEnvironmentHooksAppend:
    """``DISTLIFT_HOOKS_*`` merges after TOML layers."""

    def test_appends_after_toml(self) -> None:
        """Env-derived specs follow file layer specs for the same event."""

        base = RawConfig(
            source="file",
            hooks=hooks_config_from_mapping({"tag_pushed": ["from_toml"]}),
        )
        env = {
            "DISTLIFT_HOOKS_TAG_PUSHED": "from_env",
        }
        env_layer_data = load_environment_config(env)
        assert "hooks_append" in env_layer_data
        env_layer = RawConfig(
            source="environment",
            hooks_append=env_layer_data["hooks_append"],
        )
        resolved = merge_config_layers([base, env_layer])
        specs = resolved.hooks.tag_pushed

        assert len(specs) == 2
        assert specs[0].shell == "from_toml"
        assert specs[1].shell == "from_env"


class TestRunHookSpecs:
    """Subprocess invocation behavior."""

    def test_argv_uses_shell_false(self, tmp_path) -> None:
        """Argv hooks call ``subprocess.run`` without a shell."""

        spec = HookSpec(argv=["/usr/bin/true"])

        with patch("distlift.hooks.subprocess.run") as run_mock:
            run_mock.return_value = MagicMock(
                returncode=0, stdout="", stderr=""
            )
            run_hook_specs(
                [spec],
                repo_root=tmp_path,
                extra_env={"DISTLIFT_EVENT": "build_succeeded"},
            )

        args, kwargs = run_mock.call_args
        assert args[0] == ["/usr/bin/true"]
        assert kwargs["shell"] is False

    def test_nonzero_raises(self, tmp_path) -> None:
        """A failing subprocess raises ``HookExecutionError``."""

        spec = HookSpec(shell="exit 1")

        with patch("distlift.hooks.subprocess.run") as run_mock:
            run_mock.return_value = MagicMock(
                returncode=1, stdout="out", stderr="err"
            )

            with pytest.raises(HookExecutionError):
                run_hook_specs(
                    [spec],
                    repo_root=tmp_path,
                    extra_env={"DISTLIFT_EVENT": "x"},
                )


class TestHookValidation:
    """``validate_hooks_config`` guards invalid specs."""

    def test_rejects_both_shell_and_argv(self) -> None:
        """A spec cannot combine ``shell`` and ``argv``."""

        bad = HooksConfig(
            tag_pushed=[HookSpec(shell="a", argv=["b"])],
        )
        cfg = ResolvedConfig(hooks=bad)

        with pytest.raises(ConfigurationError):
            validate_hooks_config(cfg)


class TestSpecsForEvent:
    """Event name lookup."""

    def test_unknown_event(self) -> None:
        """Invalid event names raise ``ValueError``."""

        cfg = HooksConfig()

        with pytest.raises(ValueError):
            specs_for_event(cfg, "not_a_real_event")


class TestBuildHookEnv:
    """Environment payload for subprocesses."""

    def test_omits_unset_optional_keys(self, tmp_path) -> None:
        """Unset optional values are absent from the mapping."""

        env = build_hook_env(
            event="release_failed",
            repo_root=tmp_path,
            dry_run=False,
        )

        assert "DISTLIFT_TAG_NAMES" not in env
        assert "DISTLIFT_ERROR" not in env
