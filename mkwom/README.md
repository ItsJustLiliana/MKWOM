# Patch manager

| File | Role |
|---|---|
| `__init__.py` | Patcher format/tool version |
| `delta.py` | Bounded COPY/literal binary delta encoder and decoder |
| `package.py` | Runtime/setup-only patch packaging, path checks and original/target hashes |
| `installer.py` | Locked install/update/uninstall with retained originals and crash-recovery journal |
| `cli.py` | GitHub channel updates, current-endpoint configuration and managed game launch |
