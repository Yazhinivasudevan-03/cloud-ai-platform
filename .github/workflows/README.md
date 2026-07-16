# CI/CD (GitHub Actions)

Four workflows, verified live against a real GitHub Actions runner (see
[`../../docs/PHASE_9.md`](../../docs/PHASE_9.md) for run results):

- `backend-ci.yml` - pytest against a real MySQL 8.0 service container
- `frontend-ci.yml` - eslint + `tsc -b && vite build`
- `ml-models-ci.yml` - pytest against a real MySQL 8.0 service container (separate test DB from the backend's)
- `docker-build.yml` - builds all three Docker images on every relevant push/PR; on pushes to `main`, also pushes to GHCR (`ghcr.io/<owner>/cloud-ai-platform-{backend,frontend,ml-models}`) using the automatic `GITHUB_TOKEN` - no external registry credentials needed

An equivalent `Jenkinsfile` (repo root) mirrors the same stages for Jenkins,
per the original spec naming both tools - see its header comment for the
honest disclosure that no live Jenkins server exists in this environment to
run it against.
