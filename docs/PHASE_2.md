# Phase 2 — Core Domain REST APIs, Expanded RBAC

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 2 of ~10
Status: **Complete and verified**

---

## 1. Overview

Phase 2 builds the core domain REST APIs on top of the Phase 1 foundation:
full CRUD for `projects`, `microservices`, `deployments`, and `pods`, each with
pagination, filtering, and sorting, following the same Clean
Architecture/Repository Pattern layering established in Phase 1. It also
expands RBAC from a single implicit `viewer` role into a real three-tier
model (`viewer` / `operator` / `admin`) with admin-managed role assignment
endpoints, backed by a data-only Alembic migration that seeds the roles.

As with Phase 1, every file below is a complete implementation, and the full
CRUD hierarchy (project → microservice → deployment → pod) plus every RBAC
boundary was exercised through real HTTP requests against the running Docker
stack before this phase was marked complete.

## 2. Objectives Completed

- [x] Full CRUD REST APIs for `projects`, `microservices`, `deployments`, `pods`
- [x] Pagination (`page`/`page_size`), filtering (name/language/status/namespace), and sorting (`sort_by`/`order`) on every list endpoint
- [x] Parent-existence validation (e.g. creating a microservice under a non-existent project returns `404`, not a foreign-key crash)
- [x] Uniqueness conflict handling (`409`) scoped correctly per parent (e.g. two projects can't share a name; two deployments *can* share a name if they're in different namespaces)
- [x] Three-tier RBAC: `viewer` (read), `operator` (read+write), `admin` (read+write+delete+user/role management) — a deliberate design decision documented in §3
- [x] Admin-only role management endpoints: `POST /users/{id}/roles`, `DELETE /users/{id}/roles/{role_name}`
- [x] Data-only Alembic migration seeding the three roles, idempotent against roles already created by Phase 1's lazy `viewer` creation
- [x] 27 new integration tests (41 total across both phases), all passing against real MySQL
- [x] End-to-end manual verification: full project→microservice→deployment→pod creation, filter/sort/pagination, and every RBAC boundary (viewer denied write, operator denied delete, admin succeeds) via live HTTP against the Dockerized stack

## 3. RBAC Design Decision (read this before anything else in this phase)

Phase 1 only had one role (`viewer`, auto-assigned) and a single admin-gated
endpoint. Phase 2 needed a real permission model for create/update/delete
across four resource types, and there are two standard ways to do that:

1. **Ownership-based** (multi-tenant SaaS style): a user can only manage resources they own; roles are secondary.
2. **Role-based, platform-wide** (internal ops-tool style): a user's role determines what actions they can take on *any* resource; ownership is metadata, not a gate.

This platform is modelled as **option 2**: an internal cloud-ops monitoring
tool used by one organization's own staff to monitor and manage its own
infrastructure — not a SaaS product isolating separate customers' data from
each other. Under that framing, an SRE with the `operator` role should be
able to register a deployment under *any* project, not just ones they
personally created, and a `viewer` (e.g. an engineer checking on a colleague's
service) should be able to read *any* project's status.

Concretely:
- `viewer` (auto-assigned to every new user): read (`GET`) access to every project/microservice/deployment/pod.
- `operator`: everything `viewer` can do, plus `POST`/`PUT` (create/update) on every project/microservice/deployment/pod.
- `admin`: everything `operator` can do, plus `DELETE`, plus user/role management (`POST`/`DELETE /users/{id}/roles`).
- `is_superuser=True` bypasses all role checks (from Phase 1, unchanged).

`projects.owner_id` is still recorded (set to whoever created the project) for
audit/attribution, but it is **not** consulted by any authorization check in
this phase. This is a explicit simplification worth revisiting if the
platform ever needs to host multiple genuinely separate organizations.

## 4. Features Implemented

| Resource | Create | Read (list, paginated/filtered/sorted) | Read (by ID) | Update | Delete |
|---|---|---|---|---|---|
| Project | operator/admin | any authenticated user | any authenticated user | operator/admin | admin |
| Microservice (nested under project) | operator/admin | any authenticated user | any authenticated user | operator/admin | admin |
| Deployment (nested under microservice) | operator/admin | any authenticated user | any authenticated user | operator/admin | admin |
| Pod (nested under deployment) | operator/admin | any authenticated user | any authenticated user | operator/admin | admin |

Plus: `POST /users/{id}/roles`, `DELETE /users/{id}/roles/{role_name}` (admin only).

## 5. Folder Structure Additions

```
backend/app/
├── schemas/
│   ├── project.py            # ProjectCreate/Update/Read
│   ├── microservice.py        # MicroserviceCreate/Update/Read
│   ├── deployment.py          # DeploymentCreate/Update/Read + DeploymentStatus enum
│   ├── pod.py                  # PodCreate/Update/Read + PodStatus enum
│   └── role.py                 # + RoleAssignment (new)
├── repositories/
│   ├── project_repository.py
│   ├── microservice_repository.py
│   ├── deployment_repository.py
│   └── pod_repository.py
├── services/
│   ├── project_service.py
│   ├── microservice_service.py
│   ├── deployment_service.py
│   └── pod_service.py
├── controllers/
│   ├── project_controller.py
│   ├── microservice_controller.py
│   ├── deployment_controller.py
│   ├── pod_controller.py
│   └── user_controller.py      # + assign_role/remove_role (new)
└── routers/
    ├── project_router.py
    ├── microservice_router.py
    ├── deployment_router.py
    ├── pod_router.py
    └── user_router.py           # + role assignment endpoints (new)

backend/alembic/versions/
└── 59b011f59240_seed_default_roles.py   # data-only migration

backend/tests/
├── test_projects.py
├── test_microservices.py
├── test_deployments.py
├── test_pods.py
└── test_user_roles.py
```

## 6. Explanation of Every New File

### `schemas/{project,microservice,deployment,pod}.py`
Each defines `{Entity}Base` (shared fields), `{Entity}Create` (= Base),
`{Entity}Update` (all fields optional, for partial updates), and
`{Entity}Read` (adds `id`, parent FK, `created_at`/`updated_at`,
`from_attributes=True` for ORM serialization). `deployment.py` and `pod.py`
additionally define `DeploymentStatus`/`PodStatus` `StrEnum`s so status values
are validated at the schema boundary rather than accepted as free-form
strings.

### `repositories/{project,microservice,deployment,pod}_repository.py`
Each extends `BaseRepository` with entity-specific uniqueness lookups
(`get_by_name`, `get_by_project_and_name`, etc.) and a `search(...)` method
that builds a filtered, sorted, paginated `SELECT` plus a matching `COUNT`,
returning `(items, total)`. Filtering uses SQLAlchemy's `.ilike()`, which
compiles to a case-insensitive comparison on MySQL (via `LOWER(...) LIKE
LOWER(...)`) even though MySQL has no native `ILIKE` operator.

### `services/{project,microservice,deployment,pod}_service.py`
Business rules: parent-existence checks (raising `404` before ever touching
the child table), uniqueness conflict checks scoped to the correct parent
(raising `409`), and the actual create/update/delete orchestration. E.g.
`DeploymentService.create` checks uniqueness on `(microservice_id, name,
namespace)` — the same deployment name is allowed to repeat across
namespaces, matching how Kubernetes actually scopes deployment names.

### `controllers/{project,microservice,deployment,pod}_controller.py`
Translate between schemas and services, and assemble the generic
`PaginatedResponse[T]` envelope (item list + `PaginationMeta`) for list
endpoints.

### `routers/{project,microservice,deployment,pod}_router.py`
FastAPI routes implementing the RBAC policy from §3 via
`Depends(require_roles(...))` on write/delete routes, and plain
`Depends(get_current_active_user)` on read routes (since every authenticated
user has at least `viewer`). Nested resources (microservice/deployment/pod)
expose both a collection route under their parent
(`/projects/{project_id}/microservices`) and a direct-by-ID route
(`/microservices/{microservice_id}`), since callers usually have the child ID
readily available after the first fetch and shouldn't need to re-supply the
parent ID for every subsequent operation.

### `controllers/user_controller.py` (extended)
Added `assign_role`/`remove_role`: look up the user and role (each `404` if
missing), then idempotently add/remove the role from `user.roles` — assigning
a role the user already has is a no-op, not an error.

### `routers/user_router.py` (extended)
Added `POST /users/{id}/roles` and `DELETE /users/{id}/roles/{role_name}`,
both admin-only.

### `backend/alembic/versions/59b011f59240_seed_default_roles.py`
A **data-only** migration (written by hand after `alembic revision` without
`--autogenerate`, since no schema changed) that inserts `viewer`/`operator`/
`admin` into `roles` if not already present. Necessary because Phase 2's RBAC
policy references `operator`/`admin` by name, and until this migration those
rows didn't exist anywhere except `viewer` (lazily created by
`AuthService.register`).

### `tests/conftest.py` (extended)
Added: seeding the three roles directly into the test schema at session start
(mirroring the migration, since tests build their schema via
`Base.metadata.create_all` and never run Alembic migrations), and a
`make_user_with_role` factory fixture that registers a user via the real
`/auth/register` endpoint, optionally grants it a role by writing directly to
the DB (the one legitimate place to bypass the API — bootstrapping the very
first admin has no other path), and returns a valid access token.

## 7. Database Changes

No schema changes. The seed migration (`59b011f59240`) only inserts rows into
the pre-existing `roles` table.

```sql
-- Applied by the seed migration, idempotently:
INSERT INTO roles (name, description) VALUES
  ('viewer', 'Read-only access to dashboards and reports'),
  ('operator', 'Can create and update platform resources'),
  ('admin', 'Full administrative access, including user and role management');
```

## 8. API Endpoints, Request/Response/Error Payloads

All endpoints are documented live at `/docs`. Representative examples:

### `POST /api/v1/projects` (operator/admin)
Request: `{"name": "Payments Platform", "description": "Core payments infra"}`
Response `201`:
```json
{ "id": 1, "name": "Payments Platform", "description": "Core payments infra",
  "owner_id": 2, "created_at": "2026-07-15T15:32:35", "updated_at": "2026-07-15T15:32:35" }
```
Errors: `409 PROJECT_EXISTS`, `403 INSUFFICIENT_ROLE`

### `GET /api/v1/projects?name=payments&sort_by=name&order=asc&page=1&page_size=10`
Response `200`:
```json
{ "items": [ { "id": 1, "name": "Payments Platform", "...": "..." } ],
  "meta": { "total": 1, "page": 1, "page_size": 10, "total_pages": 1 } }
```

### `POST /api/v1/projects/{project_id}/microservices` (operator/admin)
Request: `{"name": "billing-service", "language": "python"}`
Response `201`: microservice object with `project_id`.
Errors: `404 PROJECT_NOT_FOUND`, `409 MICROSERVICE_EXISTS`

### `POST /api/v1/microservices/{microservice_id}/deployments` (operator/admin)
Request: `{"name": "billing-deploy", "namespace": "production", "replicas": 3, "status": "running"}`
Response `201`: deployment object. `status` must be one of `running|pending|failed|unknown` (`422` otherwise).
Errors: `404 MICROSERVICE_NOT_FOUND`, `409 DEPLOYMENT_EXISTS` (scoped to `microservice_id + name + namespace` — the same name is fine in a different namespace)

### `POST /api/v1/deployments/{deployment_id}/pods` (operator/admin)
Request: `{"pod_name": "billing-deploy-7f8d9", "node_name": "node-1", "status": "running"}`
Response `201`: pod object.
Errors: `404 DEPLOYMENT_NOT_FOUND`, `409 POD_EXISTS`

### `DELETE /api/v1/{projects,microservices,deployments,pods}/{id}` (admin only)
Response `204` (empty body). Error: `403 INSUFFICIENT_ROLE` for operator/viewer, `404` if already gone.

### `POST /api/v1/users/{id}/roles` (admin only)
Request: `{"role_name": "operator"}`
Response `200`: full `UserRead` with updated `roles` list. Idempotent — assigning twice is not an error.
Errors: `404 USER_NOT_FOUND`, `404 ROLE_NOT_FOUND`, `403 INSUFFICIENT_ROLE`

### `DELETE /api/v1/users/{id}/roles/{role_name}` (admin only)
Response `200`: `UserRead` with the role removed (no-op if it wasn't present).

## 9. Frontend / ML / Kubernetes / Monitoring

Unchanged from Phase 1 — still scaffolded only, no implementation this phase.

## 10. Docker / Environment

No changes to `Dockerfile`, `docker-compose.yml`, or environment variables
this phase — Phase 2 is pure application-layer work on top of Phase 1's
infrastructure.

## 11. Installation / Reproduction Steps

Identical to Phase 1 (§25–27 in `docs/PHASE_1.md`), plus applying the new
migration:

```powershell
docker compose up -d mysql
docker compose build backend
docker compose run --rm backend alembic upgrade head   # now also runs 59b011f59240
docker compose up -d backend
```

To exercise RBAC manually, you must bootstrap the first admin by hand (there's
no admin at all on a fresh database — this is intentional, not a bug):

```powershell
# Register a user via the API first, then grant it admin directly in MySQL:
docker exec cloud-ai-mysql mysql -u cloudai -pcloudai_password cloud_ai_platform `
  -e "INSERT IGNORE INTO user_roles (user_id, role_id) SELECT u.id, r.id FROM users u, roles r WHERE u.username='<username>' AND r.name='admin';"
```
From then on, that admin can use `POST /users/{id}/roles` to grant `operator`/`admin` to anyone else through the API.

## 12. Commands Used This Phase

```powershell
# Generate the data-only seed migration (no --autogenerate: no schema changed)
docker compose run --rm -v "${PWD}\backend:/app" backend alembic revision -m "seed default roles"

# Apply it
docker compose run --rm -v "${PWD}\backend:/app" backend alembic upgrade head

# Run the full test suite (Phase 1 + Phase 2, 41 tests)
docker compose run --rm -v "${PWD}\backend:/app" backend pytest -v

# Verify roles were seeded
docker exec cloud-ai-mysql mysql -u cloudai -pcloudai_password cloud_ai_platform -e "SELECT id, name, description FROM roles;"
```

## 13. Troubleshooting / Issues Hit This Phase

1. **Test seeding conflict**: a Phase 1 test (`test_users_list_allowed_for_admin_role`) manually created its own `Role(name="admin", ...)` row inline. Once Phase 2's `conftest.py` started seeding `admin`/`operator`/`viewer` for the whole test session, that test's manual insert violated the unique constraint on `roles.name`. Fixed by changing the test to fetch the already-seeded role instead of creating a duplicate — a good example of why seed data should live in one place (`conftest.py`) rather than being duplicated per-test.
2. **Rate limiter during manual verification**: hammering `/auth/login` repeatedly while manually testing (admin, operator, viewer logins in quick succession) tripped the same 5/minute production rate limit — again, correct behavior, not a bug. Restarting the backend container reset the in-memory counter for the purposes of continued manual testing (in real usage this just means: don't log in more than 5 times a minute, which is a reasonable production limit).
3. **Verification-script bug (not an app bug)**: an early scratch verification command accidentally reused the *admin* token instead of a viewer token in a `try {} catch {}` block intended to test viewer-denial, so it silently created a stray project ("Should Fail") rather than being denied (admins are, correctly, allowed to create projects). Caught by inspecting the database directly afterward; deleted via the API's own `DELETE /projects/{id}` and noted here as a reminder to double check test-script token wiring, not the API.

## 14. Security Notes

- RBAC checks happen server-side in `require_roles()` (Phase 1) on every write/delete route — never inferred from client-supplied data.
- Role assignment itself is admin-gated, preventing privilege escalation via the API (a `viewer`/`operator` cannot grant themselves `admin`).
- Parent-existence checks happen *before* uniqueness/creation logic, so a malformed `project_id` can't be used to probe for unrelated database errors — it always surfaces as a clean `404`.

## 15. Verification Checklist

- [x] `alembic upgrade head` applies the seed migration cleanly, idempotently (re-running is a no-op)
- [x] `pytest -v` → **41/41 tests passing** (14 from Phase 1 + 27 new) against real MySQL
- [x] Full HTTP flow: operator creates project → microservice → deployment → pod, all `201`
- [x] `GET /projects?name=...&sort_by=...&order=...&page=...&page_size=...` → correct filter, sort, and pagination metadata
- [x] Viewer: `POST /projects` → `403 INSUFFICIENT_ROLE`; `GET /projects` → `200`
- [x] Operator: `DELETE /pods/{id}` → `403 INSUFFICIENT_ROLE`
- [x] Admin: `DELETE /pods/{id}` → `204`, subsequent `GET` → `404 POD_NOT_FOUND`
- [x] `POST /users/{id}/roles` grants a role, is idempotent, and `404`s on an unknown role name

## 16. Testing Checklist

- `test_projects.py` (8 tests): RBAC on create/update/delete, duplicate-name conflict, 404 on missing project, pagination+filter+sort correctness
- `test_microservices.py` (5 tests): parent-not-found 404, duplicate-in-project conflict, language filter, RBAC on write/delete
- `test_deployments.py` (5 tests): parent-not-found 404, namespace-scoped uniqueness (same name allowed in different namespace), status filter, status update, invalid status enum rejection
- `test_pods.py` (5 tests): parent-not-found 404, duplicate-pod conflict, status filter + sort, restart-count update, RBAC on delete
- `test_user_roles.py` (4 tests): non-admin denied, idempotent grant, unknown-role 404, revoke

Run: `docker compose run --rm -v "${PWD}\backend:/app" backend pytest -v`

## 17. Next Phase Plan (Phase 3)

- Monitoring stack: Prometheus + Node Exporter + cAdvisor + kube-state-metrics + Grafana, wired into `docker-compose.yml`.
- A metrics-ingestion endpoint (or scrape-target adapter) to start populating the `metrics` and `resource_usage` tables with real data — currently empty, since Phase 2 only manages the structural entities (projects/microservices/deployments/pods), not their telemetry.
- Grafana dashboards for CPU/memory/disk/network per deployment/pod.

**Phase 3 will not start until this Phase 2 report is reviewed and confirmed.**

## 18. References

- SQLAlchemy `ilike()`: https://docs.sqlalchemy.org/en/20/core/operators.html#sqlalchemy.sql.operators.ColumnOperators.ilike
- Alembic data migrations: https://alembic.sqlalchemy.org/en/latest/cookbook.html#data-migrations
- FastAPI dependency injection (used throughout for RBAC): https://fastapi.tiangolo.com/tutorial/dependencies/
- Kubernetes deployment naming/namespacing model (informed the namespace-scoped uniqueness decision): https://kubernetes.io/docs/concepts/overview/working-with-objects/namespaces/
