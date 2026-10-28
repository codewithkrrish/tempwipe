"""Allow `python -m tempwipe` as well as the `tempwipe` console script."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
