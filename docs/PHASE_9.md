# Phase 9 — CI/CD (GitHub Actions + Jenkins)

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 9 of ~10
Status: **Complete, verified on a real GitHub Actions runner**

---

## 1. Overview

Phase 9 automates what every previous phase's "Verification Results" section
did by hand: run the backend's pytest suite against a real MySQL database,
lint and build the frontend, run the ml-models pytest suite against its own
test database, and build (and now publish) all three Docker images - on
every push, not just when a phase happens to finish.

This phase also crossed a threshold none of Phases 1-8 needed to: the
project had no git repository at all until this phase. Git itself was not
installed on the machine, and there was no GitHub remote. Both were set up
from scratch as the first step (§4), then a real GitHub repository was
created and the workflows below were verified by actually pushing to it and
watching GitHub's own infrastructure run them - not `act` or any other local
Actions emulator, and not a `--dry-run`.

## 2. Objectives Completed

- [x] Git installed, repository initialized, `.gitignore` audited and fixed (§4) before the first commit
- [x] Real GitHub repository created: [github.com/Yazhinivasudevan-03/cloud-ai-platform](https://github.com/Yazhinivasudevan-03/cloud-ai-platform) (public)
- [x] `backend-ci.yml` - pytest against a real MySQL 8.0 service container
- [x] `frontend-ci.yml` - eslint + `tsc -b && vite build`
- [x] `ml-models-ci.yml` - pytest against a separate MySQL 8.0 service container (own test database, mirroring the local test suite's isolation - see Phase 4)
- [x] `docker-build.yml` - builds all 3 images on every relevant push/PR; pushes to GHCR on `main` using the automatic `GITHUB_TOKEN` (no external registry credentials configured or needed)
- [x] `Jenkinsfile` - equivalent pipeline stages for Jenkins, since the original spec names both GitHub Actions and Jenkins (honest disclosure: not run against a live Jenkins server - see §6)
- [x] **All four GitHub Actions workflows verified with real, successful runs** against the pushed repository - including one real bug found and fixed by an actual failed run, not caught by inspection (§5)

## 3. Architecture Decisions

### Path-scoped triggers, one workflow per component
Each of `backend-ci.yml`/`frontend-ci.yml`/`ml-models-ci.yml` triggers only
on changes under its own directory (plus its own workflow file), mirroring
this project's existing separation of the three deployable units (their own
`Dockerfile`s, their own dependency files, their own test suites since Phase
1/4/7). A frontend-only change does not spin up a MySQL service container
for nothing, and vice versa.

### Real MySQL service containers, not SQLite or mocks
Every backend and ml-models test-related decision in this project has
insisted on a real MySQL schema (`backend/tests/conftest.py`'s own docstring:
"Tests run against a real MySQL schema (not SQLite) so behaviour matches
production exactly"). CI honors that: both `backend-ci.yml` and
`ml-models-ci.yml` use GitHub Actions' `services:` block to run an actual
`mysql:8.0` container alongside the test job, with `MYSQL_DATABASE` set
directly to the test schema name each suite's `conftest.py` expects
(`cloud_ai_platform_test` / `cloud_ai_platform_ml_test`) - the MySQL image's
own entrypoint then grants the created user privileges on exactly that
database, with no extra `GRANT` step needed.

### GHCR over a third-party registry
`docker-build.yml` pushes to GitHub Container Registry
(`ghcr.io/<owner>/cloud-ai-platform-{backend,frontend,ml-models}`) using the
workflow-provided `GITHUB_TOKEN`, rather than Docker Hub/ECR/GCR. This
required zero secrets to be configured by hand - a real advantage for a
dissertation project with no existing cloud registry account - while still
being a genuine, working, pull-able container registry, not a
build-and-discard step.

### Jenkinsfile provided, but disclosed as unverified
The original spec names both GitHub Actions and Jenkins under "CI/CD". A
`Jenkinsfile` mirroring the same four stages (backend test, frontend build,
ml-models test, Docker build) is included at the repo root, using the Docker
Pipeline plugin's `docker.image(...).withRun(...)` idiom for ephemeral MySQL
containers - the same real-database principle as the GitHub Actions
workflows. Unlike those workflows, **no Jenkins controller/agent exists in
this environment**, so this file has not been executed against a live
server. It is complete and follows established Jenkins Pipeline syntax, not
a stub - but it carries a materially weaker verification guarantee than the
GitHub Actions workflows, and its own header comment says so explicitly.

## 4. Setting Up Git and GitHub From Scratch

Neither git nor a repository existed before this phase:

```powershell
winget install --id Git.Git -e
winget install --id GitHub.cli -e
```

Before the first commit, `.gitignore` was audited against what was actually
on disk (not assumed correct) - `ml-models/{lstm,isolation_forest,random_forest}/artifacts/`
contained real generated files (`model.keras`, `.pkl`, `evaluation.png`,
`metadata.json`) that the existing `.gitignore` only partly excluded
(`*.h5`/`*.pkl`/`checkpoints/` - missing `.keras` and `.png`/`.json`
entirely). Fixed by excluding the whole `artifacts/` directories instead of
enumerating file extensions one at a time, and confirmed via
`git diff --cached --name-only` before committing that no `.env`,
`node_modules/`, `frontend/dist/`, `__pycache__/`, or model artifact ever got
staged.

```powershell
git init
git config user.name "Yazhinivasudevan-03"
git config user.email "..."
git add -A && git commit -m "Initial commit: Phases 1-8 complete"

gh auth login                    # interactive - run by the user, not automatable
gh repo create cloud-ai-platform --public --source=. --remote=origin
git branch -M main
git push -u origin main
```

## 5. Verification Results

**Verified live**, by pushing to the real repository at
[github.com/Yazhinivasudevan-03/cloud-ai-platform](https://github.com/Yazhinivasudevan-03/cloud-ai-platform)
and watching GitHub's own Actions runners execute (`gh run list` / `gh run view --log`):

| Workflow | Result | Duration | What it proved |
|---|---|---|---|
| Frontend CI | ✅ success | 48s | `npm ci` + eslint + `tsc -b && vite build` all clean on a fresh Ubuntu runner |
| Backend CI | ✅ success | 2m29s | Full pytest suite passing against a real MySQL 8.0 service container |
| ML Models CI | ✅ success | 1m44s | Pytest suite passing against its own separate MySQL test database, TensorFlow installed cleanly |
| Docker Build (1st attempt) | ❌ **failure** | 21s | Caught a real bug - see below |
| Docker Build (2nd attempt, after fix) | ✅ success | 2m59s | All 3 images built and **actually pushed to GHCR** with real digests |

**One real bug, caught by an actual failing run, not by inspection:**
the first `docker-build.yml` run failed in 21 seconds with
`ERROR: failed to build: invalid tag "ghcr.io/Yazhinivasudevan-03/cloud-ai-platform-frontend:latest": repository name must be lowercase`.
`github.repository_owner` reflects the GitHub username/org exactly as
registered - this account's own username contains uppercase letters, and
Docker/GHCR repository names must be all-lowercase. GitHub Actions'
expression syntax (`${{ }}`) has no built-in lowercasing function, so this
was fixed with a real shell step using bash's `${VAR,,}` lowercase
parameter expansion, writing the result to `$GITHUB_ENV` for later steps to
use (`docker-build.yml`'s "Compute lowercase image owner" step) - not
special-cased to this one username, so it is correct for any account.

**Confirmed pushed to GHCR** (from the successful run's own build logs, not
assumed from a green checkmark):

```
pushing manifest for ghcr.io/yazhinivasudevan-03/cloud-ai-platform-backend:latest@sha256:eea67eb5...
pushing manifest for ghcr.io/yazhinivasudevan-03/cloud-ai-platform-frontend:latest@sha256:07f6b7d0...
pushing manifest for ghcr.io/yazhinivasudevan-03/cloud-ai-platform-ml-models:latest@sha256:c5848cf6...
```

Each image was also tagged with its triggering commit SHA
(`...:04945f63ee18b4c8cbddf9fdc251695583b1ec80`) alongside `:latest`, so a
specific build is always traceable back to the exact commit that produced it.

## 6. Known Limitations (disclosed, not hidden)

- **Jenkinsfile is unverified against a live server** - no Jenkins controller/agent exists in this environment. See §3's dedicated note.
- **No deployment step** - `docker-build.yml` builds and publishes images but does not `kubectl apply`/`helm upgrade` against any cluster. Auto-deploying from CI to a machine-local Docker Desktop Kubernetes cluster (Phase 8) would not generalize to any real reader of this dissertation, so it is intentionally left as a manual step (`docs/PHASE_8.md` §6) rather than faked into a workflow that could never work outside this exact machine.
- **GHCR packages default to private visibility** even in a public repository, until manually toggled to public in the GitHub UI (Package settings → Change visibility) - not something a workflow run itself can prove or change; this is disclosed rather than assumed.
- **No branch protection / required status checks configured** - the workflows run and report status, but nothing yet blocks a merge on their failure. Reasonable for a single-contributor dissertation repository; would be a real gap for a team project.

## 7. Verification Checklist

- [x] Git installed, repository initialized, `.gitignore` audited and corrected before first commit
- [x] Real GitHub repository created and pushed to
- [x] `backend-ci.yml` - real successful run against a live MySQL service container
- [x] `frontend-ci.yml` - real successful run (lint + build)
- [x] `ml-models-ci.yml` - real successful run against a live MySQL service container
- [x] `docker-build.yml` - real failure caught and fixed, then a real successful run with confirmed GHCR pushes (digests captured above)
- [x] `Jenkinsfile` written, complete, and honestly disclosed as unverified against a live server

## 8. Next Phase Plan (Phase 10)

- Load/performance testing (JMeter/Locust against the running stack), a security-hardening pass (dependency audit, checking the OWASP items named in the original spec against what's actually implemented), and final consolidated documentation.

**Phase 10 will not start until this Phase 9 report is reviewed and confirmed.**

## 9. References

- GitHub Actions `services:` (job service containers): https://docs.github.com/actions/using-containerized-services/about-service-containers
- `docker/build-push-action`: https://github.com/docker/build-push-action
- GitHub Container Registry: https://docs.github.com/packages/working-with-a-github-packages-registry/working-with-the-container-registry
- Jenkins Declarative Pipeline syntax: https://www.jenkins.io/doc/book/pipeline/syntax/
- Jenkins Docker Pipeline plugin: https://plugins.jenkins.io/docker-workflow/
- Bash lowercase parameter expansion (`${VAR,,}`): https://www.gnu.org/software/bash/manual/html_node/Shell-Parameter-Expansion.html
