from typer.testing import CliRunner

from distlift.cli import app

runner = CliRunner()


class TestCLI:
    def test_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "distlift" in result.output.lower()

    def test_release_simple_no_selector_fails(self):
        result = runner.invoke(app, ["release", "simple"])
        assert result.exit_code != 0

    def test_release_simple_two_selectors_fails(self):
        result = runner.invoke(app, ["release", "simple", "--major", "--minor"])
        assert result.exit_code != 0

    def test_config_show_runs(self, tmp_path):
        result = runner.invoke(app, ["config", "show", "--repo-root", str(tmp_path)])
        assert result.exit_code == 0

    def test_plugins_list_runs(self, tmp_path):
        result = runner.invoke(app, ["plugins", "list", "--repo-root", str(tmp_path)])
        assert result.exit_code == 0
