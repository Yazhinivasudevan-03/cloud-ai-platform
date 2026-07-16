# Monitoring

Implemented in Phase 3 — see [`docs/PHASE_3.md`](../docs/PHASE_3.md) for full detail.

- `prometheus/prometheus.yml` - scrape config for Prometheus itself, Node Exporter,
  cAdvisor, and the FastAPI backend's own `/metrics`. Alerting rules are deferred
  to Phase 5 (Alerting).
- `grafana/dashboards/platform-overview.json` - a 6-panel dashboard (API request
  rate/latency, backend container CPU/memory, host CPU/memory)
- `grafana/provisioning/` - datasource (Prometheus, fixed uid `prometheus_ds`) and
  dashboard auto-provisioning config, so Grafana comes up fully configured with
  no manual UI steps

**kube-state-metrics is intentionally not deployed** - it requires a real
Kubernetes API server to introspect, which doesn't exist until Phase 8. Its
scrape job is present in `prometheus.yml`, commented out, ready to enable then.

**Known environment limitation:** on Docker Desktop for Windows/Mac, cAdvisor
cannot enumerate individual container metadata (a documented upstream
overlay2/storage-driver incompatibility with Docker Desktop's VM) — it is
still up and scraped successfully, and will report full per-container metrics
correctly on a native Linux host or a real Kubernetes node. Details in
`docs/PHASE_3.md` §8.
