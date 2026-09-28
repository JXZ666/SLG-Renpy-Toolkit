#!/usr/bin/env python
"""Windowed entry point for the SLG-Renpy-Toolkit GUI executable."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import appgui  # noqa: E402


def main(argv=None):
    """Launch only the GUI, optionally opening the dropped game folder."""
    if argv is None:
        argv = sys.argv[1:]
    initial_dir = argv[0] if argv else None
    appgui.main(initial_dir=initial_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
