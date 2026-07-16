# Phase 8 — Kubernetes Manifests + Helm Chart

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 8 of ~10
Status: **Complete, fully verified on a real cluster**

---

## 1. Overview

Phase 8 moves the entire stack built in Phases 1-7 (MySQL, backend, frontend,
Prometheus, Grafana, Node Exporter, cAdvisor, ml-models) from Docker Compose
onto Kubernetes, as both a flat set of raw manifests (`kubernetes/base/`,
tied together with Kustomize) and an equivalent parameterized Helm chart
(`kubernetes/helm/cloud-ai-platform/`). This is not a mechanical 1:1 port:
two components are genuinely rebuilt rather than copy-pasted, because a real
cluster finally exists to support them properly -

- **cAdvisor** is no longer a standalone container. Every Kubernetes node's
  kubelet already exposes container metrics natively at
  `/metrics/cadvisor`; Prometheus reaches it through the API server's node
  proxy. Running a separate cAdvisor DaemonSet on top of that would be
  redundant with what the platform already gets for free.
- **kube-state-metrics** is enabled for real. Phase 3's monitoring stack
  deferred it with the reasoning "it needs a real Kubernetes API server to
  introspect - meaningless against Docker Compose." That cluster now exists.

Both the raw-manifest path and the Helm chart were verified end-to-end
against a real, local Kubernetes cluster (Docker Desktop's Kubernetes,
enabled by the user partway through this phase) - see §8.

## 2. Objectives Completed

- [x] Namespace, non-secret ConfigMap, placeholder Secret (`kubernetes/base/`)
- [x] Dynamically-provisioned PVCs for mysql/prometheus/grafana/ml-models artifacts, plus one illustrative static PersistentVolume example (not applied by default)
- [x] MySQL: Deployment (deliberately not a StatefulSet - §3) + Service + init-script ConfigMap
- [x] Backend: Deployment (2 replicas, `alembic upgrade head` initContainer, Prometheus scrape annotations) + Service + HorizontalPodAutoscaler
- [x] Frontend: Deployment (2 replicas) + Service - the exact same Docker image as Docker Compose, zero modifications (§3)
- [x] Ingress routing to the frontend (which already proxies `/api/` internally - no separate API path rule needed)
- [x] Prometheus: ServiceAccount/ClusterRole/ClusterRoleBinding + a from-scratch `kubernetes_sd_configs` scrape config (4 jobs: self, node-cadvisor, node-exporter, kube-state-metrics, plus pod-annotation discovery) + Deployment + Service
- [x] Node Exporter as a DaemonSet (not a Deployment - §3)
- [x] kube-state-metrics: scoped RBAC + Deployment + Service, enabled for the first time in this project
- [x] Grafana: datasource/dashboard-provider/dashboard ConfigMaps (dashboard rewritten for real Kubernetes cAdvisor labels) + Deployment + Service
- [x] ml-models: consolidated PVC + a one-off Job (full pipeline run) + a CronJob (daily re-prediction), both excluded from the always-on Kustomize/Helm install - applied explicitly, mirroring `docker-compose.yml`'s `profiles: ["ml"]` treatment of the same service
- [x] `kubernetes/base/kustomization.yaml` tying the always-on raw manifests together
- [x] A full Helm chart (`kubernetes/helm/cloud-ai-platform/`) templating the identical architecture, `values.yaml`-parameterized
- [x] **Full live verification on a real cluster** - not just `kubectl apply --dry-run` or `helm template` - see §8

## 3. Architecture Decisions

### Deployment, not StatefulSet, for MySQL
A StatefulSet is the textbook-correct primitive for a database (stable
network identity, ordered/graceful scaling, one PVC per replica via
`volumeClaimTemplates`) - but this platform runs exactly one non-clustered
MySQL instance, matching the single `mysql` container in `docker-compose.yml`.
The extra machinery StatefulSet exists for (multi-replica identity/ordering)
has nothing to do here. `strategy: Recreate` ensures Kubernetes never runs
two MySQL pods against the same PVC, even momentarily during a rollout; the
Deployment is deliberately not exposed via HPA.

### DaemonSet, not Deployment, for Node Exporter
Node Exporter must run exactly one instance per node to report that node's
own hardware/OS metrics. A Deployment's replica count has no relationship to
node count, so it is the wrong primitive - this is also the one thing Docker
Compose's single `node-exporter` container structurally could not model at
all, since Compose has no concept of "nodes." `hostNetwork`/`hostPID` plus
mounting the host's `/proc`/`/sys` read-only are what let it see the node's
real metrics instead of its own container's, and a permissive toleration
(`operator: Exists`) lets it schedule onto tainted nodes too.

### Job/CronJob for ml-models, excluded from the always-on install
`backoffLimit: 0` and `restartPolicy: Never`: an ML run that fails partway
(e.g. mid-training) should not be blindly retried by Kubernetes the way a
stateless web request would be - a human should look at why it failed
first. Both the Job (full pipeline) and CronJob (daily re-prediction only)
are intentionally excluded from `kustomization.yaml` and disabled by default
in the Helm chart (`mlModels.job.enabled` / `mlModels.cronJob.enabled`,
both `false`) - they are one-off/scheduled batch workloads applied
explicitly, exactly mirroring `docker-compose.yml`'s `profiles: ["ml"]`.

### Dynamic PVCs vs. the static PersistentVolume example
The platform's real storage (mysql/prometheus/grafana/ml-models) uses
dynamically-provisioned PVCs against the cluster's default StorageClass
(Docker Desktop's is named `hostpath`) - no capacity planning or manual
volume creation needed. `kubernetes/base/persistent-volume-example.yaml`
exists purely to satisfy and demonstrate the literal "Persistent Volume" (as
opposed to "Persistent Volume Claim") requirement, since a real
dynamic-provisioning setup never needs a hand-written PV object. It is
explicitly excluded from `kustomization.yaml` and not applied by default.

### RBAC scoped to what this platform's own dashboards use
Both Prometheus and kube-state-metrics need cluster-wide read access (nodes,
pods, the kubelet's cAdvisor proxy for Prometheus; workload/PV/PVC/HPA
resource types for kube-state-metrics) - hence `ClusterRole`/
`ClusterRoleBinding`, not namespaced `Role`s. kube-state-metrics' `ClusterRole`
here is deliberately scoped to only the resource types this platform's own
Grafana dashboards use (nodes/pods/services/namespaces/PV/PVC/configmaps;
deployments/daemonsets/replicasets/statefulsets; jobs/cronjobs; HPAs) rather
than the exhaustive list in kube-state-metrics' official upstream manifest,
which grants read access to nearly every resource type in the cluster for a
general-purpose install.

### `kubernetes_sd_configs`, replacing Docker Compose's static target list
`monitoring/prometheus/prometheus.yml` (Docker Compose) hard-coded container
hostnames as scrape targets. The Kubernetes-native rewrite
(`kubernetes/base/prometheus-configmap.yaml`) instead uses `role: node` and
`role: pod` service discovery with relabeling - the `kubernetes-pods` job
specifically keys off `prometheus.io/scrape`/`port`/`path` pod annotations,
which the backend Deployment sets on its own pod template, so any future pod
can opt in to being scraped just by adding those three annotations.

### HPA and Ingress both require add-ons Docker Desktop doesn't ship by default
`backend-hpa.yaml` (`autoscaling/v2`, CPU target 60% - the same
`OPTIMIZATION_TARGET_CPU_PERCENT` this platform's own recommendation engine
uses in Phase 6's `scale_deployment` HPA-formula calculation) requires
**metrics-server**, and `ingress.yaml` requires an **ingress-nginx**
controller. Neither ships with Docker Desktop Kubernetes out of the box -
exact install commands used during verification are in §7.

## 4. Folder Structure

```
kubernetes/
├── base/                                  # Raw manifests, tied together with Kustomize
│   ├── namespace.yaml
│   ├── configmap-backend.yaml
│   ├── secret-backend.yaml                # placeholder values - see file header
│   ├── mysql-init-configmap.yaml
│   ├── mysql-pvc.yaml / prometheus-pvc.yaml / grafana-pvc.yaml / ml-models-pvc.yaml
│   ├── persistent-volume-example.yaml      # illustrative only - NOT in kustomization.yaml
│   ├── mysql-deployment.yaml / mysql-service.yaml
│   ├── backend-deployment.yaml / backend-service.yaml / backend-hpa.yaml
│   ├── frontend-deployment.yaml / frontend-service.yaml
│   ├── ingress.yaml
│   ├── prometheus-rbac.yaml / prometheus-configmap.yaml / prometheus-deployment.yaml / prometheus-service.yaml
│   ├── node-exporter-daemonset.yaml
│   ├── kube-state-metrics.yaml             # ServiceAccount+ClusterRole+ClusterRoleBinding+Deployment+Service
│   ├── grafana-configmap.yaml / grafana-deployment.yaml / grafana-service.yaml
│   ├── ml-models-job.yaml / ml-models-cronjob.yaml  # NOT in kustomization.yaml - applied explicitly
│   └── kustomization.yaml
└── helm/cloud-ai-platform/                 # Equivalent Helm chart
    ├── Chart.yaml
    ├── values.yaml
    └── templates/
        ├── _helpers.tpl                    # shared `cloud-ai-platform.labels`
        ├── namespace.yaml / configmap-backend.yaml / secret-backend.yaml / mysql-init-configmap.yaml
        ├── storage.yaml                    # all 4 PVCs, one file
        ├── mysql-deployment.yaml / mysql-service.yaml
        ├── backend-deployment.yaml / backend-service.yaml / backend-hpa.yaml
        ├── frontend-deployment.yaml / frontend-service.yaml
        ├── ingress.yaml
        ├── prometheus-rbac.yaml / prometheus-configmap.yaml / prometheus-deployment.yaml / prometheus-service.yaml
        ├── node-exporter-daemonset.yaml / kube-state-metrics.yaml
        ├── grafana-configmap.yaml / grafana-deployment.yaml / grafana-service.yaml
        ├── ml-models-job.yaml / ml-models-cronjob.yaml   # gated behind mlModels.job.enabled / mlModels.cronJob.enabled
        └── NOTES.txt
```

## 5. Explanation of Key Files

### `kubernetes/base/backend-deployment.yaml` / `templates/backend-deployment.yaml`
`imagePullPolicy: Never` (default in Helm too), because Docker Desktop's
Kubernetes shares its Docker Engine's image store - no registry push needed
for local/dev use. An `initContainer` runs `alembic upgrade head` against the
same image before the main container starts, so migrations always apply
before the API begins serving traffic. Pod-template annotations
(`prometheus.io/scrape`/`port`/`path`) are what the `kubernetes-pods`
Prometheus job discovers.

### `kubernetes/base/backend-service.yaml` and `frontend-deployment.yaml`
The Services are deliberately named `mysql`, `backend`, and `frontend` -
exactly the hostnames already baked into the existing container configs
(the backend's `MYSQL_HOST` env var, the frontend's `nginx.conf`
`proxy_pass http://backend:8000/api/`). This is what lets the exact same
Docker images from Phases 1-7 run completely unmodified between Docker
Compose and Kubernetes.

### `kubernetes/base/prometheus-configmap.yaml` / `templates/prometheus-configmap.yaml`
The `kubernetes-nodes-cadvisor` job is the one genuinely new piece: it
scrapes `https://kubernetes.default.svc:443/api/v1/nodes/${node}/proxy/metrics/cadvisor`
using the Prometheus pod's own ServiceAccount token for bearer auth - this
is the API-server-proxied route to the kubelet's native cAdvisor endpoint,
replacing the standalone `cadvisor` container from Docker Compose entirely.

### `kubernetes/helm/cloud-ai-platform/values.yaml`
Parameterizes everything meaningful: image repo/tag/pullPolicy per
component, replica counts, resource requests/limits, PVC sizes, ingress
host/class, all backend config values, all placeholder secret values (same
disclosure as `kubernetes/base/secret-backend.yaml` - these are template
values like `.env.example`, never real credentials), the full monitoring
stack's enabled/image fields, and an `mlModels` section with `job.enabled`/
`cronJob.enabled` toggles (both default `false`).

## 6. Command Reference

```powershell
# Raw manifests (Kustomize)
kubectl apply -k kubernetes/base
kubectl -n cloud-ai-platform get pods
kubectl delete -k kubernetes/base          # tear down

# metrics-server (required for backend-hpa.yaml to report real CPU%)
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
# Docker Desktop's kubelet serving certs aren't valid for metrics-server's
# default TLS verification - patch in the documented workaround:
kubectl patch deployment metrics-server -n kube-system --type=json `
  -p '[{"op":"add","path":"/spec/template/spec/containers/0/args/-","value":"--kubelet-insecure-tls"}]'
kubectl -n cloud-ai-platform get hpa

# ingress-nginx (required for ingress.yaml to route anywhere)
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.11.3/deploy/static/provider/cloud/deploy.yaml
kubectl -n ingress-nginx get svc ingress-nginx-controller   # EXTERNAL-IP is "localhost" on Docker Desktop

# ml-models batch workloads (excluded from the always-on install)
kubectl apply -f kubernetes/base/ml-models-job.yaml
kubectl apply -f kubernetes/base/ml-models-cronjob.yaml

# Helm chart
cd kubernetes/helm/cloud-ai-platform
helm lint .
helm template cloud-ai-platform .
helm install cloud-ai-platform . --create-namespace -n cloud-ai-platform
helm upgrade cloud-ai-platform . -n cloud-ai-platform
helm uninstall cloud-ai-platform -n cloud-ai-platform
```

To reach the app through the Ingress without editing the OS hosts file
(what verification in §8 used), send the `Host` header directly:

```powershell
Invoke-WebRequest -Uri "http://localhost/" -Headers @{Host="cloud-ai-platform.local"}
```

For a persistent setup, add `127.0.0.1 cloud-ai-platform.local` to
`C:\Windows\System32\drivers\etc\hosts` instead (requires admin rights - not
done automatically by any script here, since it's a machine-wide change).

## 7. Prerequisites Not Shipped by Docker Desktop Kubernetes

| Add-on | Why it's needed | Install command |
|---|---|---|
| `metrics-server` | `backend-hpa.yaml` / `backend.hpa` cannot read real CPU utilization without it - `kubectl get hpa` shows `<unknown>` and never scales | See §6; needs the `--kubelet-insecure-tls` patch on Docker Desktop specifically |
| `ingress-nginx` | `ingress.yaml` / `templates/ingress.yaml` has no controller to satisfy it without this - the Ingress object applies successfully but routes nowhere | See §6 |

Neither is installed automatically by `kubectl apply -k` or the Helm chart -
both are cluster-wide add-ons a real environment would already have, not
something an application's own manifests should assume ownership of
installing.

## 8. Verification Results

**Verified live**, against a real Kubernetes cluster (Docker Desktop
Kubernetes v1.34.1, single-node, enabled by the user partway through this
phase):

- `kubectl apply -k kubernetes/base` - all 30 resources created without error
- All 9 pods reached `Running`/`Ready` (2× backend, 2× frontend, mysql, prometheus, grafana, kube-state-metrics, node-exporter); the backend's `alembic upgrade head` initContainer hit one transient `Init:Error` (`Connection refused` - MySQL was still finishing its first-run initialization) and self-healed via Kubernetes' automatic backoff retry once MySQL became ready, with no manual intervention
- `GET /health` and `GET /health/db` on the backend Service both returned `ok`, confirmed via `kubectl port-forward` - the backend is genuinely connected to MySQL through the cluster network, not just started
- `metrics-server` installed and patched with `--kubelet-insecure-tls`; `backend-hpa` went from `cpu: <unknown>/60%` to a real `cpu: 5%/60%` reading, correctly holding at 2 replicas (well under the scale-up threshold)
- `ingress-nginx` installed; `ingress-nginx-controller` Service got `EXTERNAL-IP: localhost` (Docker Desktop's automatic LoadBalancer exposure)
- **Full path verified end-to-end**: `GET http://localhost/` with `Host: cloud-ai-platform.local` → `200`, the real built HTML shell; `POST http://localhost/api/v1/auth/login` (same Host header, invalid credentials) → `422`, a genuine FastAPI validation response - proving the complete chain (ingress-nginx → frontend Service → frontend's own nginx `/api/` proxy → backend Service → FastAPI) works, not just the static frontend in isolation
- **Prometheus's Kubernetes-native service discovery confirmed functionally correct, not just syntactically valid YAML** - queried `/api/v1/targets` directly and every job reported `health: up`:

  | job | targets up |
  |---|---|
  | `prometheus` (self) | 1/1 |
  | `kubernetes-nodes-cadvisor` | 1/1 (the kubelet-proxy replacement for the old standalone cAdvisor container) |
  | `kubernetes-node-exporter` | 1/1 |
  | `kube-state-metrics` | 1/1 |
  | `kubernetes-pods` (annotation-based) | 2/2 (both backend pods) |

- All 4 PVCs (`mysql-pvc`, `prometheus-pvc`, `grafana-pvc`, `ml-models-artifacts-pvc`) reached `Bound` against the `hostpath` default StorageClass, confirming dynamic provisioning works as designed
- **Helm chart validated two ways**: (1) `helm lint` and `helm template` - clean, all 27 expected resource kinds render, the ml-models Job/CronJob correctly absent by default and correctly present when `--set mlModels.job.enabled=true`; (2) a **real** `helm install` (not just `--dry-run`) into the same namespace after tearing down the raw-manifest deployment (Helm refuses to adopt resources it didn't create, and the raw manifests and Helm chart both name their ClusterRoles identically since they template the same architecture - they cannot coexist on one cluster, by design, same as choosing Docker Compose *or* Kubernetes, not both) - the Helm-installed stack was re-verified with the identical health/HPA/ingress checks above, with identical results

**One real, self-healing issue observed, not a bug**: the backend's
migration initContainer failing once with `Connection refused` before MySQL
finished initializing is expected Kubernetes behavior (nothing in this
project's manifests orders MySQL's *readiness*, as opposed to its
existence, ahead of the backend's initContainer) - Kubernetes' own restart
backoff resolved it without any change needed.

## 9. Known Limitations (disclosed, not hidden)

- **Placeholder secrets everywhere** (`secret-backend.yaml`, Helm's `values.yaml` `secrets` section) - same disclosure as `backend/.env.example`. A real deployment must override every value and should prefer Sealed Secrets or the External Secrets Operator over a plain Helm-templated `Secret` entirely.
- **Single-node cluster** - Docker Desktop Kubernetes only ever has one node, so the DaemonSet behavior (node-exporter running per-node) is verified structurally correct but not tested across multiple nodes.
- **No real DNS for the Ingress host** - `cloud-ai-platform.local` was reached via an explicit `Host` header rather than an `/etc/hosts` entry, since editing the OS hosts file is a machine-wide change this project's automation does not make unprompted (see §6 for the one-line addition a user can make themselves).
- **Grafana admin password is the literal string `admin`** by default (`GF_SECURITY_ADMIN_PASSWORD`, marked `# CHANGE ME` in both the raw manifest and `values.yaml`) - fine for local verification, not for anything else.
- **The raw manifests and the Helm chart cannot run on the cluster simultaneously** - both template the same cluster-scoped RBAC object names (`ClusterRole/prometheus`, `ClusterRole/kube-state-metrics`) by design, since they are two equivalent ways to deploy the identical architecture, not two different things meant to coexist.

## 10. Verification Checklist

- [x] `kubectl apply -k kubernetes/base` succeeds, all resources created
- [x] All pods reach `Running`/`Ready` (self-healed one transient init race, unassisted)
- [x] Backend confirmed connected to MySQL through the cluster (`/health/db` → `ok`)
- [x] `metrics-server` installed + patched; HPA reports real CPU utilization
- [x] `ingress-nginx` installed; Ingress routes to the frontend
- [x] Full request path verified end-to-end (ingress → frontend nginx → backend Service → FastAPI)
- [x] Prometheus's Kubernetes-native service discovery confirmed - all 5 scrape jobs `up`, including the kubelet-cAdvisor-proxy replacement job
- [x] All PVCs `Bound` via dynamic provisioning
- [x] `helm lint` / `helm template` clean, correct resource set, ml-models toggle verified both ways
- [x] Real `helm install` into a live cluster succeeded and was independently re-verified

## 11. Next Phase Plan (Phase 9)

- CI/CD via GitHub Actions: lint + test (backend pytest, frontend `tsc`/build) on every push/PR, Docker image builds for backend/frontend/ml-models, and a documented (not necessarily auto-deployed, given this is a local dissertation environment) path to applying the Phase 8 manifests/Helm chart.

**Phase 9 will not start until this Phase 8 report is reviewed and confirmed.**

## 12. References

- Kustomize: https://kubectl.docs.kubernetes.io/guides/introduction/kustomize/
- Helm: https://helm.sh/docs/
- metrics-server: https://github.com/kubernetes-sigs/metrics-server
- ingress-nginx: https://kubernetes.github.io/ingress-nginx/
- kube-state-metrics: https://github.com/kubernetes/kube-state-metrics
- Kubernetes HPA (`autoscaling/v2`): https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/
- Prometheus `kubernetes_sd_config`: https://prometheus.io/docs/prometheus/latest/configuration/configuration/#kubernetes_sd_config
- Docker Desktop Kubernetes: https://docs.docker.com/desktop/kubernetes/
