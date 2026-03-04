from typer.testing import CliRunner
from kodadocs.main import app

runner = CliRunner()


def test_mcp_command_exists():
    """The 'mcp' subcommand is registered and shows in help."""
    result = runner.invoke(app, ["mcp", "--help"])
    assert "No such command" not in result.output


def test_mcp_command_in_help():
    """The 'mcp' command appears in the main help output."""
    result = runner.invoke(app, ["--help"])
    assert "mcp" in result.output
