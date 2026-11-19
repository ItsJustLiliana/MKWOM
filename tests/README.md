# Tests

`test_patcher.py` exercises install/update/uninstall, user-data preservation, real channel selection, launch
environment, malformed deltas, unsupported builds, path traversal, modified files and transaction recovery.
Run `python -m pytest -q`. The build workflow separately tests the actual Linux server protocol and round-trips the
official v0.1.15 Windows runtime. Real multiplayer races require operator acceptance tests.

`test_deployment.py` checks Linux deployment/executable rollback and preserving newer account writes, CA and relay
configuration with mocked service control. It is skipped on Windows because the deployment target is Linux.
