# Suggested first message to your coding agent

You are in the `karmada-hybrid-lab-agent-handoff-v4` repository, a **starter**, not a fully working deployment. First read `AGENTS.md`, `docs/ARCHITECTURE_DECISIONS.md`, `docs/IMPLEMENTATION_PLAN.md`, and `docs/ACCEPTANCE_TESTS.md` in full. Do not change locked decisions.

Your goal is a reproducible Karmada v1.19.1 kind/WSL2 hybrid bursting laboratory. It has 4 named clusters (`karmada-mgmt`, `dc-primary`, `dc-secondary`, `cloud-azure`), Alloy/Prometheus/Loki/Grafana in mgmt with PVCs and 24h metrics/log retention, default Loki-based Grafana annotations, Windows FreeLens, no ingress, and two demos (manual burst; then real CPU-driven FederatedHPA burst).

**Top priority:** the base bootstrap MUST automatically install and verify *all* FederatedHPA prerequisites (metrics-server in all 3 members and Karmada metrics-adapter/APIService in mgmt). There must be no manual adapter installation step. A preliminary script has been added, but its behavior has not been tested against real kind/Karmada. Do not assume it works.

Start with an audit and dependency graph, then implement and execute stages P0/P1. Show commands and evidence for every success/failure. Continue through observability, scenarios and end-to-end tests if host execution is available. Make conservative fixes; prefer official version-pinned sources. Update the README and verification results. Do not claim end-to-end success if you cannot actually run the cluster.

Report at checkpoints: files changed, tests passed, blockers, next action. Ask me only if a decision requires changing the agreed architecture or if you need permission/access for host actions.
