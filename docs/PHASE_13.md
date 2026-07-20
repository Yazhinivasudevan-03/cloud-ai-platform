# Phase 13 — Separate Database for Login Credentials

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 13 (post-completion feature addition, beyond the original 10-phase plan)
Status: **Complete and verified**

---

## 1. Overview

Requested directly as "create a separate new database for the login
credentials of the users." Login credentials (`users`, `roles`,
`user_roles`) now live in their own MySQL database (`cloud_ai_auth`) on
the same MySQL server, fully isolated from the rest of the application's
data (`cloud_ai_platform`) - a compromise, backup/restore, or query
against one database can no longer touch the other. Six existing tables
(`api_keys`, `audit_logs`, `cloud_provider_accounts`, `notifications`,
`projects`, `settings`) reference `users.id` and continue to do so via
cross-database foreign keys, which MySQL supports natively on a single
server.

## 2. Objectives Completed

- [x] `users`, `roles`, `user_roles` moved into a new `cloud_ai_auth` database, with all existing data (41 users, 3 roles, 46 role assignments in the dev database) preserved exactly - zero rows lost, zero downtime beyond the migration itself
- [x] All 6 referencing tables' foreign keys re-pointed across the database boundary, `ondelete` behavior unchanged
- [x] `AUTH_MYSQL_DATABASE` setting (default `cloud_ai_auth`) added, consistently threaded through `.env.example`, Docker Compose, the Kubernetes ConfigMap, and the Helm chart's `values.yaml`
- [x] Backend test suite: 149/149 passing, exercising the cross-database schema from scratch via `Base.metadata.create_all` against a dedicated `cloud_ai_auth_test` database
- [x] `alembic revision --autogenerate` produces a genuinely empty diff against the live post-migration database - the ORM models and the real schema match exactly, including a cosmetic index-naming fix
- [x] Live verification: registered and logged in a real user through the actual nginx-proxied frontend (`http://localhost:3000`, not the backend directly), confirming the cross-database join for role lookup and every pre-existing project/deployment/notification still resolves its owning user correctly after the migration

## 3. Architecture Decisions

### Same MySQL server, new schema - not a fully separate database instance
Asked directly which of two approaches to take: (a) a second schema on
the same MySQL server, keeping cross-database foreign keys, or (b) a
fully separate MySQL container/instance with no DB-level referential
integrity at all (requiring all 6 referencing tables' ownership checks to
move from the database to the application layer). The user chose (a).
This is a genuine separate database - a different backup, a different set
of grants, a different set of files on disk - while keeping the six
existing FK constraints working exactly as before, at far lower risk and
migration cost than extracting a true separate auth microservice this
close to the dissertation deadline.

### `RENAME TABLE`, not copy-then-drop
The dev database already held real registered users (41 of them) before
this migration ran. `RENAME TABLE users TO cloud_ai_auth.users` moves a
table (and every row, and its `AUTO_INCREMENT` counter) between databases
on the same server instantly, with no data duplication window and no risk
of a partial copy. The alternative - `CREATE TABLE ... LIKE` followed by
`INSERT INTO ... SELECT` followed by `DROP TABLE` - would work but adds
a copy step that simply isn't necessary within one MySQL server.

### Foreign keys must be dropped before the rename, then recreated schema-qualified
MySQL will not let a table be renamed out of a database while other
tables hold live foreign key constraints against it. The migration
therefore: (1) drops all 8 constraints referencing `users`/`roles`
(6 application tables + `user_roles`'s own 2), (2) renames the 3 auth
tables into `cloud_ai_auth`, (3) recreates all 8 constraints with an
explicit `referent_schema` (and, for `user_roles` itself, `source_schema`,
since the table now lives in `cloud_ai_auth` too). Constraint names were
looked up directly from `information_schema.KEY_COLUMN_USAGE` on the live
database beforehand and reused, rather than guessed.

### `AUTH_SCHEMA` as a single source of truth, not a hardcoded string per file
`app/models/user.py` computes `AUTH_SCHEMA = get_settings().AUTH_MYSQL_DATABASE`
once at import time; every other model that references `users.id` imports
this constant rather than hardcoding `"cloud_ai_auth"`. This is what makes
the test suite's schema override (`AUTH_MYSQL_DATABASE=cloud_ai_auth_test`,
set in `conftest.py` before any model import - mirroring the existing
`MYSQL_DATABASE` override) apply consistently everywhere without touching
six files every time the schema name might change.

### `include_schemas=True` needs an explicit `include_name` filter on MySQL (real bug, found and fixed)
Enabling `include_schemas=True` in `alembic/env.py` (necessary for
autogenerate to even see the `cloud_ai_auth` tables) initially broke
autogenerate entirely: MySQL's information-schema-based reflection tries
to inspect *every* database visible on the server - including `mysql`,
`performance_schema`, and `sys` - and the application's `cloudai` MySQL
user has no read access to those, so the very first `alembic revision
--autogenerate` after this change failed with `Access denied for user
'cloudai'@'%' to database 'performance_schema'`. Fixed with an
`include_name` callback that restricts schema inspection to exactly
`cloud_ai_platform` and `cloud_ai_auth`, filtering out every system
schema and every `*_test` database before autogenerate touches them.

### A cosmetic index-naming diff, fixed rather than ignored
After the migration, `alembic revision --autogenerate` still reported one
difference: `roles`'s auto-generated index for its unique `name` column
was named `ix_roles_name` in the live database (created back when `Role`
had no schema) but the model now computes `ix_cloud_ai_auth_roles_name`
for a fresh table (SQLAlchemy's unnamed-index naming incorporates the
schema once one is set). Functionally identical index, but left alone it
would have shown up as permanent, harmless-looking noise on every future
autogenerate run. Renamed in place (`ALTER TABLE ... RENAME INDEX`,
folded into the same migration) so autogenerate now reports a genuinely
empty diff.

## 4. Verification Results

- Backend test suite: **149/149 passing**, unchanged in count from Phase 12 - this phase is a pure infrastructure change, no new endpoints or business logic
- Migration applied to the live dev database: `41 users`, `3 roles`, `46 user_roles` rows confirmed intact in `cloud_ai_auth` post-migration via direct `SELECT COUNT(*)`; `SHOW TABLES` on `cloud_ai_platform` confirms `users`/`roles`/`user_roles` are gone from there entirely
- `information_schema.KEY_COLUMN_USAGE` confirms all 8 foreign keys (`api_keys`, `audit_logs`, `cloud_provider_accounts`, `notifications`, `projects`, `settings`, and `user_roles`'s own 2) now point at `cloud_ai_auth.users` / `cloud_ai_auth.roles`
- `alembic revision --autogenerate` after the migration generates a genuinely empty `upgrade()`/`downgrade()` pair - the live schema and the ORM models match exactly, cross-database schema and all
- Live end-to-end verification through the real nginx-proxied frontend (`http://localhost:3000/api/...`): registered a fresh user, logged in, fetched `/auth/me` (which resolves the user's roles across the database boundary via `user_roles`), and listed pre-existing projects created *before* this migration - each one's `owner_id` still resolves correctly against the moved `users` table
- Test data created during verification was deleted afterward, not left in the shared dev database

## 5. Follow-Up: Frontend Container Healthcheck Fix

Immediately after this phase's live verification, a standing, unrelated
bug was noticed: `docker compose ps` reported the frontend container as
"unhealthy" continuously (`FailingStreak` over 150 checks). Investigation
found nginx itself was working correctly the entire time - every real
request in the container logs succeeded - the healthcheck itself was
broken: `frontend/Dockerfile`'s `HEALTHCHECK` ran `wget http://localhost:80/`,
and `nginx.conf` only binds IPv4 (`listen 80` => `0.0.0.0:80`), but
`localhost` resolves to the IPv6 loopback first inside the container,
where nothing listens, so every check hit "Connection refused" against a
server that was actually fine. Confirmed directly: `wget http://localhost:80/`
failed, `wget http://127.0.0.1:80/` succeeded immediately, and `netstat`
showed nginx bound only to `0.0.0.0:80`. Fixed by pointing the healthcheck
at `127.0.0.1` explicitly - the container now reports `healthy`.

Re-verified afterward with a full browser walkthrough (Dashboard,
Projects, Cloud Accounts, and a Deployment detail page including the
Phase 12 Cloud Sync tab): correct MUI theming, sidebar navigation with
accurate active-page highlighting, populated tables and charts, and a
working dark-mode toggle, confirming the healthcheck fix (and the
Phase 12/13 changes preceding it) introduced no visual regressions.

## 6. Known Limitations (disclosed, not hidden)

- **Not a fully separate database instance.** Both databases still share one MySQL server/container/volume - a genuine logical and access-control separation, but not physical isolation. A true separate auth microservice (its own container, its own volume, no DB-level FK at all) was considered and explicitly declined in favor of this lower-risk approach - see the architecture decision above.
- **No password/credential-format changes.** This phase only relocates *where* credentials are stored, not *how* - passwords are still bcrypt-hashed exactly as before; nothing about the authentication logic itself changed.
