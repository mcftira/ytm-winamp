"""PyInstaller entry point for the ytm-winamp exe."""
import sys

from ytm_winamp.cli import main

if __name__ == "__main__":
    sys.exit(main())
