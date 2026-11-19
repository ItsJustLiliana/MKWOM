# Build, publish and deploy tools

| File | Role |
|---|---|
| `entry.py` | Packaged patcher executable entry point |
| `prepare_source.py` | Fetch pinned upstream and apply multiplayer source patch |
| `build_client.py` | Runtime-only Windows build, official archive validation, binary patch and install/uninstall round-trip |
| `server_release.py` | Linux server-only release archive with identity/checksum and licenses |
| `release_metadata.py` | Actions candidate identity and SHA-256 inventory |
| `channel.py` | Channel pointer manifest for immutable patch assets |
| `activate_channel.py` | Verify published assets before updating a channel pointer |
| `promote.py` | Promote unchanged tested candidate artifacts to Beta or a draft Release |
| `remote_deploy.py` | Transfer verified artifacts through administrator Tailscale SSH |
| `deploy_server.py` | Existing user-service update with stopped-writer backup, health checks and executable rollback |

Each script's opening docstring describes invocation. Deployment scripts are Linux-only and never provision a
public server, firewall or player database implicitly. See `docs/operations.md` before enabling deployment.
