"""Entry point for ``python -m distlift``."""

from distlift.cli import app


def main() -> None:
    """Run the Typer CLI using ``sys.argv``.

    Args:
        None
    """
    app()


if __name__ == "__main__":
    main()
