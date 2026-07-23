# Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices

An MSc dissertation project: a cloud-native platform for real-time cloud/Kubernetes
monitoring, AI-driven workload prediction, anomaly detection, failure prediction,
intelligent alerting, resource optimization, and cost monitoring for microservices.

## Project status

**All 10 phases complete.** Built phase by phase - see [`docs/`](docs/) for a detailed, honestly-verified report for each phase.

| Phase | Scope | Status |
|---|---|---|
| 1 | Project scaffolding, normalized MySQL schema (19 tables), JWT authentication + RBAC | **Complete** - see [`docs/PHASE_1.md`](docs/PHASE_1.md) |
| 2 | Core domain APIs (projects/microservices/deployments/pods), pagination/filtering/sorting, 3-tier RBAC | **Complete** - see [`docs/PHASE_2.md`](docs/PHASE_2.md) |
| 3 | Monitoring stack (Prometheus, Node Exporter, cAdvisor, Grafana) + metrics ingestion API | **Complete** - see [`docs/PHASE_3.md`](docs/PHASE_3.md) |
| 4 | AI module (LSTM forecasting, Isolation Forest anomaly detection, Random Forest failure prediction) as an independent batch pipeline + read-only prediction API | **Complete** - see [`docs/PHASE_4.md`](docs/PHASE_4.md) |
| 5 | Alerting + notifications (dashboard/email/Slack/Telegram), automatic + on-demand rule engine | **Complete** - see [`docs/PHASE_5.md`](docs/PHASE_5.md) |
| 6 | Resource optimization (8 recommendation types incl. HPA-style scaling) + cost prediction engine | **Complete** - see [`docs/PHASE_6.md`](docs/PHASE_6.md) |
| 7 | Frontend (React + TypeScript + MUI dashboards, dark mode, Recharts + Chart.js) | **Complete** - see [`docs/PHASE_7.md`](docs/PHASE_7.md) (visual browser verification not possible in this environment - disclosed there) |
| 8 | Kubernetes manifests + Helm chart, verified live on a real cluster | **Complete** - see [`docs/PHASE_8.md`](docs/PHASE_8.md) |
| 9 | CI/CD (GitHub Actions, verified on a real runner + Jenkinsfile) | **Complete** - see [`docs/PHASE_9.md`](docs/PHASE_9.md) |
| 10 | Load/performance testing (Locust + JMeter, both run live), security hardening (dependency audits, rate limiting, security headers), Postman collection | **Complete** - see [`docs/PHASE_10.md`](docs/PHASE_10.md) |
| 11 | Self-service cloud provider accounts (any provider, unlimited count, per-account region) | **Complete** - see [`docs/PHASE_11.md`](docs/PHASE_11.md) |
| 12 | Real-time cloud metrics sync (real AWS CloudWatch via boto3, scheduled + on-demand) | **Complete** - see [`docs/PHASE_12.md`](docs/PHASE_12.md) |
| 13 | Separate database for login credentials (users/roles isolated from application data, same MySQL server) | **Complete** - see [`docs/PHASE_13.md`](docs/PHASE_13.md) |
| 14 | Consolidated cloud account usage view (live CPU/memory/network per account, at a glance) | **Complete** - see [`docs/PHASE_14.md`](docs/PHASE_14.md) |
| 15 | Connect cloud accounts (AWS/Azure/GCP/Other) directly from the Dashboard | **Complete** - see [`docs/PHASE_15.md`](docs/PHASE_15.md) |
| 16 | Per-account monitoring as the primary view (dedicated page per account with its own usage + alerts, trimmed navigation, verified at scale) | **Complete** - see [`docs/PHASE_16.md`](docs/PHASE_16.md) |
| 17 | Reliability polish (VPA manifest, retry/backoff on external calls, recommendation cooldown + safety limits) | **Complete** - see [`docs/PHASE_17.md`](docs/PHASE_17.md) |
| 18 | Production hardening: DB backup CronJob, self-signed TLS on Ingress, real audit logging, broadened rate limiting, NetworkPolicy, ML retraining schedule, LSTM-forecast-informed optimization | **Complete** - see [`docs/PHASE_18.md`](docs/PHASE_18.md) |
| 19 | Production hardening continued: real AWS Cost Explorer billing sync (moto-tested, no live AWS account available - disclosed); CD pipeline (`helm upgrade`, built and documented but disabled pending a real cluster's `KUBE_CONFIG`); SMS notification channel (Twilio, self-service phone number via `PATCH /auth/me`); frontend automated tests (Vitest + React Testing Library, wired into CI); structured JSON logging + OpenTelemetry distributed tracing (live-verified, trace_id-correlated); optimization recommendation auto-apply (off by default, live-verified) | **Complete** - see [`docs/PHASE_19.md`](docs/PHASE_19.md) |
| 20 | Notification Settings page (per-user channels/DND/credentials, encrypted) + per-cloud-account CPU/memory alert threshold overrides; real memory alerting added as a prerequisite (previously CPU-only) | **Complete** - see [`docs/PHASE_20.md`](docs/PHASE_20.md) |

## Known limitations (honestly disclosed, not glossed over)

These are the specific gaps carried by real infrastructure/credentials
that were not available in the environment this project was built in -
each is written up in full in its own phase document, not just listed
here as a bullet:

- **No live AWS billing account** - the real AWS Cost Explorer
  integration (`app/integrations/aws_cost_explorer.py`, Phase 19 item 9)
  is verified against moto's Cost Explorer emulation only. moto has no
  mechanism to be seeded with cost data at all (real AWS has no API to
  inject billing data either - it's generated internally from actual
  usage), so parsing-logic tests use a patched boto3 client with
  realistic fixture responses instead of a live account's real numbers.
- **No live Kubernetes cluster** - the CD pipeline
  (`.github/workflows/cd-deploy.yml`, Phase 19 item 10) is genuinely
  wired up (`helm upgrade --install` against the exact GHCR images
  `docker-build.yml` just pushed) but stays disabled: its `deploy` job
  only runs once a `KUBE_CONFIG` repository secret exists, and none is
  configured. It has been verified via `helm lint`/`helm template` only -
  the `deploy` job itself has never actually executed against a real
  cluster.
- **No live Twilio account** - the SMS notification channel
  (`app/notifications/sms_notifier.py`, Phase 19 item 11) is verified
  against a mocked `httpx.post` call shaped like a real Twilio request,
  not a real delivered text message.
- **No live OTLP collector** - distributed tracing
  (`app/observability/tracing.py`, Phase 19 item 13) defaults to a
  `ConsoleSpanExporter` (genuinely verified live against the running
  `cloud-ai-backend` container - see `docs/PHASE_19.md` §6 for the
  captured trace_id-correlated log/span pair) but the OTLP export path
  to a real collector (Jaeger/Tempo/an OTel Collector) is verified only
  via a mocked exporter-constructor call, not a real network export.

See [`docs/PHASE_18.md`](docs/PHASE_18.md) and
[`docs/PHASE_19.md`](docs/PHASE_19.md) for the full detail behind each of
these, including what *was* verified and how.

## Repository layout

```
cloud-ai-platform/
  backend/         FastAPI REST API (Clean Architecture, Repository Pattern)
  frontend/        React + TypeScript + MUI dashboard (Vite, dockerized via nginx)
  ml-models/       LSTM / Isolation Forest / Random Forest models - independent batch pipeline (own Docker image, run via `docker compose --profile ml run`)
  database/        Schema init scripts, seed data, backups
  docker/          Shared Docker assets
  kubernetes/      K8s manifests (kustomize) + Helm chart, verified live on a real cluster (Phase 8)
  monitoring/      Prometheus/Grafana config for Docker Compose (Kubernetes uses its own config in kubernetes/base + the Helm chart - see docs/PHASE_8.md)
  scripts/         Operational scripts
  docs/            Phase-by-phase technical documentation
  tests/           Load tests (Locust + JMeter, tests/load/) and API tests (Postman, tests/postman/) - see docs/PHASE_10.md
  .github/         GitHub Actions workflows (backend/frontend/ml-models CI + Docker build/push to GHCR) - see docs/PHASE_9.md
  docker-compose.yml
  Jenkinsfile      Equivalent Jenkins pipeline (spec names both tools) - not run against a live server, see docs/PHASE_9.md
```

Live repository: [github.com/Yazhinivasudevan-03/cloud-ai-platform](https://github.com/Yazhinivasudevan-03/cloud-ai-platform)

## Quick start

```powershell
# from the repository root
copy .env.example .env
docker compose up -d mysql
docker compose build backend
docker compose run --rm backend alembic upgrade head   # applies schema + seeds viewer/operator/admin roles
docker compose up -d      # backend + frontend + mysql + prometheus + grafana + node-exporter + cadvisor
```

Frontend: http://localhost:3000
API docs: http://localhost:8000/docs
Health check: http://localhost:8000/health
Prometheus: http://localhost:9090
Grafana: http://localhost:3001 (default `admin`/`admin` — change via `.env`)

Every new user gets the `viewer` role automatically (read-only). To create/update
resources or manage users, an existing admin must grant `operator`/`admin` via
`POST /api/v1/users/{id}/roles` — see [`docs/PHASE_2.md`](docs/PHASE_2.md) §11
for how to bootstrap the very first admin.

To run the AI pipeline against a deployment you've created (see `docs/PHASE_4.md` §10):

```powershell
docker compose build ml-models
docker compose --profile ml run --rm ml-models all --deployment-id <id> --pod-id <id>
```

Alerts are evaluated automatically every 5 minutes (configurable via
`ALERT_EVALUATION_INTERVAL_MINUTES`), or on demand as an operator/admin via
`POST /api/v1/alerts/evaluate`. Resource optimization recommendations run
automatically every 60 minutes, or on demand via `POST /api/v1/optimization/evaluate`.

To deploy the same stack on Kubernetes instead (see `docs/PHASE_8.md` for
prerequisites and full verification results):

```powershell
kubectl apply -k kubernetes/base
# or, equivalently:
helm install cloud-ai-platform kubernetes/helm/cloud-ai-platform --create-namespace -n cloud-ai-platform
```

Every push to `main` (or PR) runs the CI workflows in `.github/workflows/` -
backend/ml-models pytest suites against real MySQL service containers,
frontend lint+build, and a Docker image build that also publishes to
`ghcr.io/yazhinivasudevan-03/cloud-ai-platform-{backend,frontend,ml-models}`
on `main`. See [`docs/PHASE_9.md`](docs/PHASE_9.md) for verified run results.

To load-test the running stack (see `docs/PHASE_10.md` for full results):

```powershell
docker compose run --rm -v "${PWD}/tests/load:/mnt/load" --entrypoint python backend /mnt/load/seed_data.py
docker run --rm --network cloud-ai-platform_cloud-ai-network -v "${PWD}/tests/load:/mnt/locust" -p 8089:8089 `
  locustio/locust -f /mnt/locust/locustfile.py --host http://backend:8000
```

Or run the Postman collection with `newman run tests/postman/cloud-ai-platform.postman_collection.json`.

Every user can configure their own cloud provider accounts (any provider,
unlimited count, one region per account) under **Cloud Accounts** in the
sidebar, or via `POST /api/v1/cloud-provider-accounts` - see [`docs/PHASE_11.md`](docs/PHASE_11.md).

Link a deployment to one of your cloud accounts (Deployment detail page,
**Cloud Sync** tab) to pull real, live resource-usage metrics from that
account on a schedule or on demand - currently AWS CloudWatch (EC2 basic
monitoring) only - see [`docs/PHASE_12.md`](docs/PHASE_12.md).

Login credentials (users/roles) live in their own database on the same
MySQL server (`AUTH_MYSQL_DATABASE`, default `cloud_ai_auth`), isolated
from the rest of the application's data - see [`docs/PHASE_13.md`](docs/PHASE_13.md).

Click "View usage" on any row in **Cloud Accounts** to see every
deployment linked to that account with its live CPU/memory/network at a
glance, without opening each deployment individually - see [`docs/PHASE_14.md`](docs/PHASE_14.md).

Connect an AWS/Azure/GCP/other cloud account and view its usage right
from the **Dashboard** - the page you land on after logging in - no need
to navigate to a separate page first - see [`docs/PHASE_15.md`](docs/PHASE_15.md).

Each connected cloud account has its own dedicated monitoring page
(`/cloud-accounts/:id`, reached via "Monitor") showing that account's
linked deployments' live CPU/memory/network **and** its own active
alerts, separately from every other account - see [`docs/PHASE_16.md`](docs/PHASE_16.md).

Full instructions, commands, and troubleshooting: [`docs/PHASE_1.md`](docs/PHASE_1.md), [`docs/PHASE_2.md`](docs/PHASE_2.md), [`docs/PHASE_3.md`](docs/PHASE_3.md), [`docs/PHASE_4.md`](docs/PHASE_4.md), [`docs/PHASE_5.md`](docs/PHASE_5.md), [`docs/PHASE_6.md`](docs/PHASE_6.md), [`docs/PHASE_7.md`](docs/PHASE_7.md), [`docs/PHASE_8.md`](docs/PHASE_8.md), [`docs/PHASE_9.md`](docs/PHASE_9.md), [`docs/PHASE_10.md`](docs/PHASE_10.md), [`docs/PHASE_11.md`](docs/PHASE_11.md), [`docs/PHASE_12.md`](docs/PHASE_12.md), [`docs/PHASE_13.md`](docs/PHASE_13.md), [`docs/PHASE_14.md`](docs/PHASE_14.md), [`docs/PHASE_15.md`](docs/PHASE_15.md), [`docs/PHASE_16.md`](docs/PHASE_16.md), [`docs/PHASE_17.md`](docs/PHASE_17.md).

## Technology stack

Frontend: React, TypeScript, Material UI, Axios, React Router, Chart.js, Recharts
Backend: Python, FastAPI, Pydantic, SQLAlchemy, Alembic, JWT
AI/ML: TensorFlow, Scikit-learn, Pandas, NumPy (LSTM, Isolation Forest, Random Forest)
Database: MySQL 8.0
Infra: Docker, Kubernetes, Helm, Prometheus, Grafana
CI/CD: GitHub Actions (verified live), Jenkins (pipeline provided)
Testing: Pytest, Postman (via newman), JMeter, Locust - all run live against the stack, not just written
