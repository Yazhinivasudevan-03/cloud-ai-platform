# Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices

An MSc dissertation project: a cloud-native platform for real-time cloud/Kubernetes
monitoring, AI-driven workload prediction, anomaly detection, failure prediction,
intelligent alerting, resource optimization, and cost monitoring for microservices.

## Project status

Being built phase by phase. See [`docs/`](docs/) for a detailed report after each phase.

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
| 10 | Load/performance testing, security hardening, final docs | Not started |

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
  tests/           Cross-cutting integration/load tests
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

Full instructions, commands, and troubleshooting: [`docs/PHASE_1.md`](docs/PHASE_1.md), [`docs/PHASE_2.md`](docs/PHASE_2.md), [`docs/PHASE_3.md`](docs/PHASE_3.md), [`docs/PHASE_4.md`](docs/PHASE_4.md), [`docs/PHASE_5.md`](docs/PHASE_5.md), [`docs/PHASE_6.md`](docs/PHASE_6.md), [`docs/PHASE_7.md`](docs/PHASE_7.md), [`docs/PHASE_8.md`](docs/PHASE_8.md), [`docs/PHASE_9.md`](docs/PHASE_9.md).

## Technology stack

Frontend: React, TypeScript, Material UI, Axios, React Router, Chart.js, Recharts
Backend: Python, FastAPI, Pydantic, SQLAlchemy, Alembic, JWT
AI/ML: TensorFlow, Scikit-learn, Pandas, NumPy (LSTM, Isolation Forest, Random Forest)
Database: MySQL 8.0
Infra: Docker, Kubernetes, Helm, Prometheus, Grafana
