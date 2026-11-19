"""Executable entry point: pyinstaller --onefile --name mkwom tools/entry.py."""
from mkwom.cli import main

raise SystemExit(main())
