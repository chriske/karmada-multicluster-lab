# Validation results

This handoff kit is NOT end-to-end validated. The v3 starter was syntax checked previously. v4 makes the pinned upstream metrics-adapter installer **part of the bootstrap** but its Kubernetes runtime behavior requires validation by an agent with access to Windows/WSL2/Docker.

Use `docs/ACCEPTANCE_TESTS.md`; record actual PASS/FAIL/BLOCKED status here. Never copy sample commands as test evidence without executing them.

Local check on 2026-11-08: `bash -n scripts/*.sh install-karmada-wsl-tools.sh` passed; YAML parsing confirmed the requested image digest on every node in all four kind configurations. `make preflight` passed the naming and pinned CLI checks, then failed because Docker socket access was denied. `make -n bootstrap` shows metrics installation followed by an explicit failure for the still-unimplemented Alloy and observability stack. No Kubernetes runtime checks were executed.

| Check | Status | Evidence |
|---|---|---|
| File syntax / JSON / YAML parsing | Pending local build verification | |
| Metrics-server and Karmada adapter runtime | BLOCKED — no Windows Docker access in this package generation | |
| Four cluster bootstrap | BLOCKED — no Windows Docker access | |
| Observability and two real demos | BLOCKED — no Windows Docker access | |
