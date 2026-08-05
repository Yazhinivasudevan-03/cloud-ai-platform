# Implementation Roadmap - 10 Consolidated Milestones

This document presents the project's **32 completed implementation phases** grouped into 10 higher-level
milestones, purely for readability. **This is a documentation reorganization only** - no code, feature,
file, or piece of completed functionality was changed, moved, or removed to produce it. Every phase's
full technical detail still lives in its own untouched `docs/PHASE_N.md` file, linked below.

For the phase-by-phase detail this grouping summarizes, see the full table in [`README.md`](../README.md#project-status)
or any individual `docs/PHASE_N.md`. For the exact old→new mapping, see
[the mapping table](#mapping-table-old-phase--new-milestone) at the bottom of this document.

---

## Milestone 1 - Project Foundation & System Architecture
*Old Phases: 1, 2*

Project scaffolding, the normalized MySQL schema (19 tables), initial JWT authentication and
role-based access control, and the core domain APIs (projects, microservices, deployments, pods) with
pagination/filtering/sorting - the backend and repository architecture everything else in the project
was built on top of.

- [`docs/PHASE_1.md`](PHASE_1.md) - Project scaffolding, schema, JWT auth + RBAC
- [`docs/PHASE_2.md`](PHASE_2.md) - Core domain APIs, pagination/filtering/sorting, 3-tier RBAC

## Milestone 2 - User Authentication & Multi-Tenant Management
*Old Phase: 24*

The platform's conversion into a genuine multi-tenant SaaS product: real signup, email verification,
forgot/reset-password, and remember-me auth flows; full per-user data isolation across the entire core
domain (every project, microservice, deployment, and alert, including the notification dispatcher's
fan-out); and the matching SaaS frontend (public Landing Page, rebuilt Sign Up/Login, named-provider
onboarding, extended Profile page, full navigation).

- [`docs/PHASE_24.md`](PHASE_24.md) - Multi-tenant SaaS conversion + full per-user data isolation

## Milestone 3 - Multi-Cloud Integration
*Old Phases: 11, 22, 25, 26, 27, 30*

Everything about connecting, configuring, and correctly addressing every supported cloud provider: self
-service cloud provider accounts (any provider, unlimited count), multi-timezone support per account,
dynamic live region discovery replacing any hardcoded region data, a structured credential-configuration
workflow with real "Test Connection" validation, full IBM Cloud and DigitalOcean backend integrations,
and full global region enrichment (185 regions across all 7 providers with automatic timezone mapping).

- [`docs/PHASE_11.md`](PHASE_11.md) - Self-service cloud provider accounts
- [`docs/PHASE_22.md`](PHASE_22.md) - Multi-timezone support for cloud accounts
- [`docs/PHASE_25.md`](PHASE_25.md) - Dynamic region discovery, resource inventory, deploy/destroy provisioning
- [`docs/PHASE_26.md`](PHASE_26.md) - Cloud Credential Configuration workflow + Test Connection
- [`docs/PHASE_27.md`](PHASE_27.md) - IBM Cloud + DigitalOcean backend integrations
- [`docs/PHASE_30.md`](PHASE_30.md) - Full global region support + automatic timezone mapping

## Milestone 4 - Resource Discovery & Real-Time Monitoring
*Old Phases: 3, 12, 28, 29*

The monitoring stack (Prometheus, Node Exporter, cAdvisor, Grafana) and every real, live data-collection
path built on top of it: real-time AWS CloudWatch metrics sync, real-time metrics and billing sync for
IBM Cloud and DigitalOcean, and automatic AWS resource discovery (13 real inventory categories,
persisted resource/metric tables, scheduled sweeps, real CloudWatch metrics per instance).

- [`docs/PHASE_3.md`](PHASE_3.md) - Monitoring stack + metrics ingestion API
- [`docs/PHASE_12.md`](PHASE_12.md) - Real-time AWS CloudWatch metrics sync
- [`docs/PHASE_28.md`](PHASE_28.md) - Real-time metrics + billing sync (IBM Cloud, DigitalOcean)
- [`docs/PHASE_29.md`](PHASE_29.md) - Automatic AWS resource discovery

## Milestone 5 - Dashboard & User Interface
*Old Phases: 7, 14, 15, 16, 32*

The React/TypeScript/MUI frontend and every major UI milestone since: the consolidated cloud-account
usage view, connecting cloud accounts directly from the Dashboard, per-account monitoring as the primary
navigation view, and the Chromium browser extension (Manifest V3) as a second, independent client
alongside the web app.

- [`docs/PHASE_7.md`](PHASE_7.md) - Frontend (React + TypeScript + MUI dashboards)
- [`docs/PHASE_14.md`](PHASE_14.md) - Consolidated cloud account usage view
- [`docs/PHASE_15.md`](PHASE_15.md) - Connect cloud accounts directly from the Dashboard
- [`docs/PHASE_16.md`](PHASE_16.md) - Per-account monitoring as the primary view
- [`docs/PHASE_32.md`](PHASE_32.md) - Chromium browser extension (Manifest V3)

## Milestone 6 - AI Analytics & Resource Optimization
*Old Phases: 4, 6*

The AI module (LSTM workload forecasting, Isolation Forest anomaly detection, Random Forest failure
prediction) as an independent batch pipeline with a read-only prediction API, and the resource
optimization engine (8 recommendation types including HPA-style scaling) with cost prediction.

- [`docs/PHASE_4.md`](PHASE_4.md) - AI module (LSTM / Isolation Forest / Random Forest) + prediction API
- [`docs/PHASE_6.md`](PHASE_6.md) - Resource optimization + cost prediction engine

## Milestone 7 - Alerts & Notification System
*Old Phases: 5, 20, 21, 23, 31*

The full alerting and notification pipeline: the original rule engine and multi-channel dispatch
(dashboard/email/Slack/Telegram), per-user Notification Settings with per-account CPU/memory threshold
overrides, disk/network/cost threshold alerting, a real Notification Bell with 9 previously-missing real
alert evaluators (Cloud Usage, Storage, Pod Restart, Resource Optimization, Security, API Latency/Error
Rate, Node/Container Failure), and the Twilio SMS integration with full Notification History tracking.

- [`docs/PHASE_5.md`](PHASE_5.md) - Alerting + notifications, rule engine
- [`docs/PHASE_20.md`](PHASE_20.md) - Notification Settings page + per-account threshold overrides
- [`docs/PHASE_21.md`](PHASE_21.md) - Disk/network alert thresholds + project cost budget alerting
- [`docs/PHASE_23.md`](PHASE_23.md) - Notification Bell + 9 real alert evaluators
- [`docs/PHASE_31.md`](PHASE_31.md) - Twilio SMS SDK integration + Notification History enrichment

## Milestone 8 - Security & Cloud Operations
*Old Phases: 13, 17, 18, 19*

The production-hardening line of work: a separate, isolated database for login credentials, reliability
polish (VPA manifest, retry/backoff on external calls, recommendation cooldown/safety limits), and two
rounds of production hardening (DB backup CronJob, TLS on Ingress, real audit logging, broadened rate
limiting, NetworkPolicy, ML retraining schedule, real AWS Cost Explorer billing sync, structured logging
+ OpenTelemetry tracing).

- [`docs/PHASE_13.md`](PHASE_13.md) - Separate database for login credentials
- [`docs/PHASE_17.md`](PHASE_17.md) - Reliability polish (VPA, retry/backoff, recommendation safety limits)
- [`docs/PHASE_18.md`](PHASE_18.md) - Production hardening (backups, TLS, audit logging, NetworkPolicy)
- [`docs/PHASE_19.md`](PHASE_19.md) - Production hardening continued (billing sync, CD pipeline, tracing)

## Milestone 9 - Testing, Validation & Cloud Deployment
*Old Phases: 8, 9, 10*

Kubernetes manifests and a Helm chart verified live on a real cluster, CI/CD (GitHub Actions verified on
a real runner, plus an equivalent Jenkinsfile), and load/performance testing (Locust + JMeter, both run
live) alongside security hardening and a Postman collection.

- [`docs/PHASE_8.md`](PHASE_8.md) - Kubernetes manifests + Helm chart, verified on a real cluster
- [`docs/PHASE_9.md`](PHASE_9.md) - CI/CD (GitHub Actions + Jenkinsfile)
- [`docs/PHASE_10.md`](PHASE_10.md) - Load/performance testing + security hardening + Postman

## Milestone 10 - Final Optimization & Dissertation Readiness
*No old phase maps here - see note below*

**Honest disclosure**: unlike the other nine milestones, this one has no dedicated source phase to point
to, because this project's real history never had a separate final-cleanup phase. Every one of the 32
phases already ended with its own full regression run, live verification against real
infrastructure, and documentation update as a built-in step - bug-fixing and validation were continuous
practice throughout, not deferred to the end. **Phase 32** (the Chromium browser extension) is the most
recently completed phase and marks the point the project reached its current, dissertation-ready state -
referenced here as that milestone marker, not as a body of "final cleanup" work distinct from what
Milestone 5 already describes it as (a real feature addition, verified live against the real backend).

---

## Mapping table: Old Phase → New Milestone

| Old Phase | New Milestone | Old Phase | New Milestone | Old Phase | New Milestone | Old Phase | New Milestone |
|---|---|---|---|---|---|---|---|
| 1 | 1 | 9 | 9 | 17 | 8 | 25 | 3 |
| 2 | 1 | 10 | 9 | 18 | 8 | 26 | 3 |
| 3 | 4 | 11 | 3 | 19 | 8 | 27 | 3 |
| 4 | 6 | 12 | 4 | 20 | 7 | 28 | 4 |
| 5 | 7 | 13 | 8 | 21 | 7 | 29 | 4 |
| 6 | 6 | 14 | 5 | 22 | 3 | 30 | 3 |
| 7 | 5 | 15 | 5 | 23 | 7 | 31 | 7 |
| 8 | 9 | 16 | 5 | 24 | 2 | 32 | 5 |

All 32 old phases are accounted for above. Milestone 10 intentionally has no entry, per the disclosure
in its section.

## What did *not* change

- No code was modified.
- No file was deleted, renamed, or moved. Every `docs/PHASE_1.md` through `docs/PHASE_32.md` is byte
  -for-byte unchanged.
- No git history was rewritten - this reorganization is a new commit, not an amend or rebase.
- No feature, architecture decision, or completed functionality was altered.
- The detailed, phase-by-phase table in `README.md` is unchanged and remains the authoritative
  granular record; this document is an additional, higher-level index on top of it.
