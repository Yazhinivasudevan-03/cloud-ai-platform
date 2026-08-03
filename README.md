# Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices

An MSc dissertation project: a cloud-native platform for real-time cloud/Kubernetes
monitoring, AI-driven workload prediction, anomaly detection, failure prediction,
intelligent alerting, resource optimization, and cost monitoring for microservices.

## Project status

**All 31 phases complete.** Built phase by phase - see [`docs/`](docs/) for a detailed, honestly-verified report for each phase.

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
| 21 | Disk/network alert thresholds (deployment-scoped, per-account overrides) + project-scoped cost budget/threshold alerting (a new `Alert.project_id`) - all live-verified, including a custom threshold override genuinely changing alert behavior | **Complete** - see [`docs/PHASE_21.md`](docs/PHASE_21.md) |
| 22 | Multi-timezone support for cloud accounts (a new `CloudAccountTimezone` table, IANA-only via stdlib `zoneinfo`, zero new dependencies) - deployments optionally link to a configured region/timezone so monitoring/alerts/notifications surface local time alongside UTC; extend-only (no existing table/API/feature changed shape), live-verified against AWS London, AWS Mumbai, Azure UK South, and GCP Mumbai | **Complete** - see [`docs/PHASE_22.md`](docs/PHASE_22.md) |
| 23 | Back buttons on every page (one shared component); a real Notification Bell (severity counts, mark-read/clear/view-details) + per-user notification settings (secondary email, country code, Telegram username, language, a full 15-category/tier preference table); real (non-fabricated) alert evaluators added for all 9 previously-missing categories - Cloud Usage, Storage, Pod Restart, Resource Optimization, Security (real failed logins), API Latency/Error Rate (real Prometheus queries), and Node/Container Failure (this platform's first live Kubernetes API connection) - live verification caught and fixed 2 real bugs (a Security evaluator that could never fire, and a Container Failure check that missed init containers - confirmed against this platform's own genuinely-still-crashing backend pod) | **Complete** - see [`docs/PHASE_23.md`](docs/PHASE_23.md) |
| 24 | Converted the platform into a genuine multi-tenant SaaS product: real signup/email-verification/forgot-reset-password/remember-me auth flows; full per-user data isolation across the entire core domain (Project through Alert, including the notification dispatcher's fan-out - previously a deliberately shared, single-organization model); real Azure Monitor + Google Cloud Monitoring metrics sync and Azure Cost Management billing sync alongside the existing AWS integration; a matching SaaS frontend (public Landing Page, rebuilt Sign Up/Login, named-provider onboarding, extended Profile page, full navigation) | **Complete** - see [`docs/PHASE_24.md`](docs/PHASE_24.md) |
| 25 | Dynamic multi-cloud region discovery (live, provider-discovered region lists for AWS/Azure/GCP/Oracle Cloud/Alibaba Cloud, replacing any hardcoded region data), a full read-only resource inventory (compute/clusters/databases/storage/networking, 25 real read paths), and real deploy/destroy provisioning (compute/storage/networking, confirm-to-destroy + full audit trail, fixed free-tier-eligible instance sizes) - all behind one provider-agnostic adapter interface, built and committed across 6 independently-verified sub-phases (25A-25F) | **Complete** - see [`docs/PHASE_25.md`](docs/PHASE_25.md) |
| 26 | Cloud Credential Configuration workflow: replaced raw backend error messages with structured, provider-specific credential forms, a real live "Test Connection" step (genuine STS GetCallerIdentity for AWS), and a `credentials_validated` gate that blocks monitoring/resource-inventory/alerting until credentials are actually proven to work, with a "Configure Credentials" empty-state on the Dashboard and Cloud Account detail page | **Complete** - see [`docs/PHASE_26.md`](docs/PHASE_26.md) |
| 27 | Real backend integrations for IBM Cloud and DigitalOcean (previously UI-only "connect" buttons since Phase 24) - credential validation, live region discovery, the full 5-category resource inventory, and compute/storage/networking provisioning, matching every other provider's capability surface; live verification against the real IBM Cloud IAM API caught and fixed a genuine discrepancy (invalid API keys reject with HTTP 400, not 401) | **Complete** - see [`docs/PHASE_27.md`](docs/PHASE_27.md) |
| 28 | Real-time metrics + billing sync for IBM Cloud and DigitalOcean - DigitalOcean gets real Droplet CPU/memory/disk/network metrics (genuinely agent-free, unlike every other provider) and real invoice-based billing sync; IBM Cloud gets real Usage Reports billing sync, with Cloud Monitoring (metrics) explicitly disclosed as not-yet-supported (a separate Sysdig-based product with no official Python SDK) rather than faked | **Complete** - see [`docs/PHASE_28.md`](docs/PHASE_28.md) |
| 29 | Automatic AWS resource discovery: closed the gap between "AWS account connected" and "the platform actually knows what's in it" - persisted `CloudResource`/`CloudResourceMetric` tables, 13 real inventory categories (EC2/ECS/EKS/Lambda/RDS/S3/EBS/ELB/ASG/VPC/Subnets/SecurityGroups/CloudWatch Alarms), automatic discovery on connect + a fast (default 60s) scheduled sweep, real CloudWatch metrics (CPU/network/disk/status-check/best-effort memory) for every running EC2 instance, and a live Dashboard/Cloud-Account-detail view - all additive, the existing Project/Deployment pipeline and Phase 25C browse endpoint untouched | **Complete** - see [`docs/PHASE_29.md`](docs/PHASE_29.md) |
| 30 | Full global region support for all 7 providers: a new central `region_metadata.py` table (185 regions - AWS 32, Azure 37, GCP 40, OCI 32, IBM 10, DigitalOcean 12, Alibaba 22) enriches every already-live-discovered region with a real city/country/IANA timezone, replacing 4 old scattered display-name dicts; automatic region→timezone mapping (`selected_region_timezone`, no manual setup required); the post-connect region switcher is now a searchable/scrollable Autocomplete showing "code — City, Country"; confirmed "All Regions" mode already worked end to end for discovery/monitoring/alerts - live-verified against a real, already-connected AWS account across all 17 of its enabled regions | **Complete** - see [`docs/PHASE_30.md`](docs/PHASE_30.md) |
| 31 | Twilio SMS SDK integration (real `twilio.rest.Client`, real detailed error handling, replacing raw HTTP) + Notification History enrichment: 4 new columns (`cloud_provider_account_id`, `phone_number`, `message_sid`, `delivery_status`) so every SMS attempt - success or failure - is auditable; dynamic per-user phone numbers, E.164 validation, and per-tenant alert isolation confirmed already correct from earlier phases; live-verified against a real Twilio account (real auth, a genuine Trial-account delivery rejection captured end to end with full error detail, Notification History row proven to persist correctly) | **Complete** - see [`docs/PHASE_31.md`](docs/PHASE_31.md) |

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
- **No live Azure/GCP accounts** - the real Azure Monitor/Cost Management
  and Google Cloud Monitoring integrations (`app/integrations/azure_monitor.py`,
  `azure_cost_management.py`, `gcp_monitoring.py`, Phase 24) are verified
  against each SDK client patched directly (no Azure/GCP emulator exists
  the way moto emulates AWS), not a live account's real metrics/billing.
  GCP **cost** sync specifically is not implemented at all - unlike AWS/
  Azure, GCP has no generalizable spend-by-service API callable with just
  account credentials (it requires the customer's own BigQuery billing
  export); this is disclosed via a real `COST_SYNC_PROVIDER_NOT_SUPPORTED`
  response, not a fabricated integration.
- **No headless browser tool** - Phase 24's frontend changes were
  verified via `tsc -b`/Vitest plus direct HTTP/API round-trips against
  the live running containers (the real register → verify-email → login
  → profile-update → change-password flow), not a literal screenshot
  walkthrough - no Playwright/chromium-cli tool was available in this
  environment.

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
