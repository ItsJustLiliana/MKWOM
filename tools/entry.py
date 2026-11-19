"""Dual entry point: graphical setup by default; explicit CLI remains available for scripts."""
import sys

if __name__ == "__main__":
    if len(sys.argv) > 1:
        from mkwom.cli import main
        raise SystemExit(main())
    from mkwom.gui import main
    main()
