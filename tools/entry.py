"""PyInstaller entrypoint for setup GUI and silent native-triggered updates."""
import sys

if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--autostart":
        from mkwom.autostart import main
        raise SystemExit(main(sys.argv[2:]))
    if len(sys.argv) > 1:
        from mkwom.cli import main
        raise SystemExit(main())
    from mkwom.wizard import main
    main()
