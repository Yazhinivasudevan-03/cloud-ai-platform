# Kubernetes

Full manifests + Helm chart for the entire stack built in Phases 1-7. See
[`../docs/PHASE_8.md`](../docs/PHASE_8.md) for the complete architecture
writeup, command reference, and live-cluster verification results.

- `base/` - raw manifests, tied together with Kustomize (`kubectl apply -k kubernetes/base`)
- `helm/cloud-ai-platform/` - equivalent Helm chart (`helm install cloud-ai-platform kubernetes/helm/cloud-ai-platform --create-namespace -n cloud-ai-platform`)

Both template the identical architecture (namespace, MySQL, backend, frontend,
Ingress, Prometheus + Node Exporter + kube-state-metrics + Grafana, and an
optional ml-models Job/CronJob) and were verified end-to-end against a real
cluster - they are alternative deployment paths, not meant to run
simultaneously (both name the same cluster-scoped RBAC objects).

Requires `metrics-server` (for the backend HPA) and an `ingress-nginx`
controller (for the Ingress) - neither ships with Docker Desktop Kubernetes
by default. Exact install commands: [`../docs/PHASE_8.md`](../docs/PHASE_8.md) §6-7.
