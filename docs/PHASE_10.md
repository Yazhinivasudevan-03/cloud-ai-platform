# Phase 10 — Load/Performance Testing, Security Hardening, Final Docs

Project: Cloud Usage Monitoring and AI-Driven Predictive Resource Optimization Platform for Microservices
Phase: 10 of ~10 (final)
Status: **Complete, fully verified live**

---

## 1. Overview

Phase 10 closes out the project with the three testing tools named in the
original spec but not yet used (Postman, JMeter, Locust), a security
hardening pass across every backend/ml-models/frontend dependency, and this
final report. Nothing here is theoretical: every load test actually ran
against the live stack, every dependency bump was verified against the full
test suite, and - in the spirit of every prior phase's honest disclosure -
this phase surfaced and fixed **four real bugs**, three of them in the
testing tooling itself, not the application. Root-causing "my load test
shows 46% errors" instead of just reporting the number turned out to be the
most valuable work in this phase.

## 2. Objectives Completed

- [x] `RATE_LIMIT_REGISTER` added (`/auth/register` was the one auth endpoint with no rate limit) - unit test + live verification
- [x] `SecurityHeadersMiddleware` (backend) + equivalent nginx `add_header` directives (frontend) - `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` - verified live on real responses
- [x] Full dependency vulnerability audit: backend (`pip-audit`), ml-models (`pip-audit`), frontend (`npm audit`) - real CVEs fixed, remainder honestly documented as accepted/unreachable risk (§4)
- [x] Locust load test (`tests/load/locustfile.py`) - real headless run against the live backend, one real harness bug found and fixed (§5)
- [x] JMeter test plan (`tests/load/jmeter-test-plan.jmx`) - real run via the official-community `justb4/jmeter` Docker image (not just written and left unexecuted), one real harness bug found and fixed (§5)
- [x] Postman collection (`tests/postman/cloud-ai-platform.postman_collection.json`) - 24 requests / 37 assertions, run for real via `newman` (§6)
- [x] This report + final README pass marking the whole project complete

## 3. Real Bugs Found and Fixed This Phase

### Bug 1: `prometheus-fastapi-instrumentator==7.0.0` incompatible with the upgraded FastAPI/Starlette
Bumping `fastapi` from `0.115.6` to `0.139.0` (needed to pull in a patched
Starlette - see §4) broke every single authenticated test with
`AttributeError: '_IncludedRouter' object has no attribute 'path'` inside
the instrumentator's route-name resolution. Root-caused via the full pytest
traceback (not guessed), fixed by bumping to `prometheus-fastapi-instrumentator==8.0.2`,
which supports the newer Starlette routing internals. Full 121-test suite
re-passed after the fix.

### Bug 2: Locust's `on_start` didn't handle a failed login
The first real Locust run showed **46% of all requests failing with 401**
across almost every endpoint uniformly. Root-caused (not just re-run and
hoped away) via three escalating diagnostics: (1) 40 concurrent requests
with one known-good token - clean; (2) 60 concurrent requests interleaving
4 different valid tokens - clean; (3) a custom `asyncio`/`httpx` script
(`tests/load/diagnose_401.py`) that staggers logins first, then sustains
concurrent polling - this reproduced it exactly, showing that users whose
*login itself* got a `429` from `RATE_LIMIT_LOGIN` (all simulated users
share the test runner's one IP address) then ran every subsequent request
with no `Authorization` header at all, because the original code did
`token = response.json()["access_token"]` unconditionally - a `KeyError`
against a 429 body, silently leaving that user "logged out" for its entire
session. The server was correct the whole time (429 on the rate limit, 401
on the missing header); the bug was entirely in the test harness. Fixed
with a `_login_or_stop()` helper that checks the status code, retries on
429 with backoff, and cleanly stops the user if login never succeeds,
instead of assuming success.

### Bug 3: JMeter's infinite loop re-ran the login request every iteration
The JMeter plan's first real run showed an escalating error rate up to
**100%** as thread concurrency ramped up. This is the same category of bug
as Locust's, but structurally worse: the login sampler was a direct sibling
inside the ThreadGroup's `LoopController` (`continue_forever=true`), so
every thread re-POSTed `/auth/login` on *every* loop iteration (every 1-3s,
for the whole test duration) rather than once - hammering `RATE_LIMIT_LOGIN`
continuously. Fixed by wrapping the login sampler + JSON extractor in an
`OnceOnlyController`, exactly mirroring Locust's `on_start`-vs-`task` split.

### Bug 4: Postman collection's own test-script type mismatch
A minor one, caught by `newman`'s own assertion failure: `String(response.id)`
compared against a collection variable that Postman stores as its original
type (a number), so `'12'` was never `to.eql(12)`. Fixed by comparing the
raw (non-stringified) value.

## 4. Dependency Vulnerability Audit

Run via `pip-audit` (backend, ml-models) and `npm audit` (frontend) against
the actual installed dependency tree in each Docker image - not a static
guess from `requirements.txt` version numbers.

### Backend: 27 known vulnerabilities across 7 packages -> 1 (accepted, unreachable)

| Package | Before | After | Notes |
|---|---|---|---|
| `fastapi` | 0.115.6 | 0.139.0 | Pulled in a patched Starlette transitively |
| `starlette` (transitive) | 0.41.3 | 0.52.1 | Fixed most CVEs; see below for the one residual |
| `cryptography` | 44.0.0 | 49.0.0 | |
| `python-jose[cryptography]` | 3.3.0 | 3.5.0 | |
| `python-multipart` | 0.0.20 | 0.0.32 | |
| `python-dotenv` | 1.0.1 | 1.2.2 | |
| `pytest` | 8.3.4 | 9.1.1 | Test-only dependency |
| `pytest-asyncio` | 0.25.0 | 1.4.0 | Bumped alongside pytest (0.25.0 pins `pytest<9`) |
| `prometheus-fastapi-instrumentator` | 7.0.0 | 8.0.2 | Required by the fastapi bump - see Bug 1 |

**Remaining: `ecdsa==0.19.2`, no fix available.** This is the well-known
Minerva timing-attack CVE. python-ecdsa's maintainers explicitly consider
side-channel attacks out of scope for the project, with no fix planned,
ever. It is a transitive dependency of `python-jose[cryptography]` (used
for EC-based JWT algorithms). This backend's `ALGORITHM` setting is
hardcoded to `HS256` (HMAC, symmetric) - the vulnerable EC signing/key-
generation code path in `ecdsa` is never exercised by this application's
actual JWT operations. Documented here as an accepted, verified-unreachable
risk rather than silently ignored or falsely claimed fixed.

### ml-models: 3 known vulnerabilities across 3 packages -> 1 (accepted, unreachable)

| Package | Before | After | Notes |
|---|---|---|---|
| `python-dotenv` | 1.0.1 | 1.2.2 | |
| `pytest` | 8.3.4 | 9.1.1 | |

**Remaining: `protobuf==4.25.9`**, fix requires `>=5.29.6`, but
`tensorflow-cpu==2.17.0` pins `protobuf<5.0.0dev` - verified directly (`pip
install protobuf==5.29.6` inside the ml-models image produces an explicit
`pip check` conflict against tensorflow-cpu's own requirement), not assumed.
Bumping TensorFlow itself to a version supporting protobuf 5.x risks
breaking the Keras API surface this project's LSTM model already depends
on - out of scope for a security-hardening pass. The CVE itself
(`PYSEC-2026-1805`) is a DoS in `google.protobuf.json_format.ParseDict()`
when parsing deeply-nested, attacker-controlled `Any` messages; ml-models
never parses untrusted JSON into protobuf `Any` messages anywhere in its
own code (protobuf here is purely TensorFlow's internal model
serialization format) - documented as accepted, verified-unreachable risk,
same as `ecdsa` above.

### Frontend: 0 known vulnerabilities
`npm audit` reported clean with no changes needed.

### Full test suites re-verified after every dependency bump
- Backend: **121/121 passing** (120 existing + the new `RATE_LIMIT_REGISTER` test)
- ml-models: **4/4 passing**

## 5. Load/Performance Testing

Both tools ran against the same seeded dataset
(`tests/load/seed_data.py`: 5 projects, 10 deployments, 30 pods, 120
resource-usage rows, a `loadtest_admin` account, and a 20-account
`loadtest_viewer_N` pool - the viewer pool is created directly through
`AuthService`, bypassing the new `RATE_LIMIT_REGISTER` endpoint entirely,
since bulk-seeding 20 accounts through a rate-limited HTTP endpoint would
defeat its own purpose).

### Locust (`tests/load/locustfile.py`)

Simulates realistic traffic composition: 90% `DashboardViewerUser` (browse
projects -> microservices -> deployments -> pods/resource-usage/predictions,
plus alerts/optimization-recommendations/notifications/me - all reads, since
viewers can't write) and 10% `OperatorUser` (triggers the same on-demand
`/alerts/evaluate` and `/optimization/evaluate` endpoints APScheduler already
calls automatically every few minutes in production).

Run command:
```powershell
docker run --rm --network cloud-ai-platform_cloud-ai-network `
  -v "${PWD}/tests/load:/mnt/locust" `
  locustio/locust -f /mnt/locust/locustfile.py --host http://backend:8000 `
  --headless -u 20 -r 0.08 --run-time 400s `
  --html /mnt/locust/report.html --csv /mnt/locust/results
```

**Final clean result** (after fixing Bug 2): 4341 requests over ~400s,
**0.14% failure rate** - and even that residual is not a real failure: it's
6 occurrences of the *expected* 429 a login retry hits before succeeding
within `_login_or_stop`'s backoff loop. Every business endpoint shows 0%
failures.

| Metric | Value |
|---|---|
| Total requests | 4,341 |
| Failure rate (excl. expected login retries) | 0.00% |
| Median latency (all endpoints) | 15ms |
| p90 | 26ms |
| p99 | 250ms (dominated by `/alerts/evaluate` and `/optimization/evaluate`, the heaviest compute endpoints) |
| Peak throughput | ~15.8 req/s |
| `POST /auth/login` median | 240ms (bcrypt is deliberately slow) |
| `POST /alerts/evaluate` median | 110-120ms |
| `POST /optimization/evaluate` median | 100-130ms |
| All `GET` list/detail endpoints median | 13-19ms |

### JMeter (`tests/load/jmeter-test-plan.jmx`)

Equivalent scenario to `DashboardViewerUser`: log in once (`Once Only
Controller`), then loop `GET /projects`, `/alerts`,
`/optimization-recommendations`, `/notifications`, `/auth/me` with a 1-3s
think-time timer, 10 threads ramped over 3 minutes (safely under
`RATE_LIMIT_LOGIN`), 6-minute total duration.

Run via the community `justb4/jmeter` Docker image (pulled and run for
real - not left as an unexecuted `.jmx` file):
```powershell
docker run --rm --network cloud-ai-platform_cloud-ai-network `
  -v "${PWD}/tests/load:/mnt/jmeter" `
  justb4/jmeter -n -t /mnt/jmeter/jmeter-test-plan.jmx `
  -l /mnt/jmeter/jmeter-results.jtl -j /mnt/jmeter/jmeter.log `
  -e -o /mnt/jmeter/jmeter-report
```

**Final clean result** (after fixing Bug 3): **1,448 requests, 0.00% errors**
across the entire 6-minute run. Average response time 16ms (min 8ms, max
300ms), peak throughput ~5.4 req/s at full 10-thread concurrency. An HTML
dashboard report is generated at `tests/load/jmeter-report/index.html`.

### Why raw report files aren't committed
Both tools' generated reports (`tests/load/report.html`,
`tests/load/jmeter-report/`, `results*.csv`, `*.jtl`) are `.gitignore`d -
they're regenerable output (9+ MB across ~280 files for a single run), not
source, the same principle already applied to ml-model artifacts in Phase
1's `.gitignore`. The source test definitions (`locustfile.py`,
`seed_data.py`, `diagnose_401.py`, `jmeter-test-plan.jmx`, `viewer_pool.csv`)
are committed; the results above are the durable record.

## 6. Postman Collection (`tests/postman/cloud-ai-platform.postman_collection.json`)

24 requests across 7 folders (Auth, Projects, Microservices, Deployments,
Pods, Metrics, Alerts, Optimization, Notifications), each with real
`pm.test()` assertions (status codes, response shape, pagination metadata,
validation-rejection behavior) - not just requests with no verification.
Uses the seeded `loadtest_admin` account for write operations (a freshly
registered user only has the default `viewer` role) and a fresh
timestamped username for the register/login/me flow so repeated runs don't
collide on a unique-username constraint.

Run via `newman` (Postman's official CLI runner, installed via `npm install
-g newman`):
```powershell
newman run tests/postman/cloud-ai-platform.postman_collection.json `
  --reporters cli --reporter-json-export tests/postman/newman-results.json
```

**Result: 24/24 requests, 37/37 assertions passing** (after fixing Bug 4),
total run duration 3.3s, average response time 53ms.

## 7. Known Limitations (disclosed, not hidden)

- **`ecdsa` (backend) and `protobuf` (ml-models) CVEs remain unfixed** - both verified unreachable given this application's actual usage (HS256-only JWT; no untrusted protobuf `Any` parsing), not silently ignored - see §4.
- **Load tests ran from a single IP** (this test-runner's Docker network), so `RATE_LIMIT_LOGIN`'s per-IP keying was a genuine constraint the test harnesses had to respect (and initially didn't - see Bugs 2 and 3). Real distributed user traffic wouldn't share one IP the way this test setup necessarily does.
- **Load test scale is modest** (10-20 concurrent users, single-machine Docker Desktop backend) - appropriate for verifying correctness and establishing a baseline, not a capacity-planning benchmark for a production deployment sized for real traffic volumes.
- **No HTTPS/TLS testing** - `SecurityHeadersMiddleware` and nginx's headers are transport-independent hardening; actual TLS termination is a reverse-proxy/ingress concern (Phase 8's `ingress-nginx`), not something this phase adds certificates for.

## 8. Verification Checklist

- [x] `RATE_LIMIT_REGISTER` added, unit-tested, and confirmed live (11th registration -> 429)
- [x] Security headers confirmed present on real backend and frontend responses
- [x] Backend dependency audit: 27 -> 1 vulnerabilities (documented, unreachable)
- [x] ml-models dependency audit: 3 -> 1 vulnerabilities (documented, unreachable)
- [x] Frontend dependency audit: 0 vulnerabilities
- [x] Full backend test suite passing after all bumps (121/121)
- [x] Full ml-models test suite passing after all bumps (4/4)
- [x] Locust load test run for real, one harness bug found root-caused and fixed, clean final results (0.14% -> effectively 0% real failures)
- [x] JMeter load test run for real via Docker, one harness bug found and fixed, clean final results (0.00% errors)
- [x] Postman collection run for real via newman, one test-script bug found and fixed, 24/24 requests and 37/37 assertions passing

## 9. Project Status

**All 10 phases are now complete.** See the root `README.md` for the full
phase table and the complete `docs/PHASE_1.md` through `docs/PHASE_10.md`
series for the full build history, every architecture decision, every
verification result, and every honestly-disclosed limitation along the way.

## 10. References

- `pip-audit`: https://github.com/pypa/pip-audit
- `npm audit`: https://docs.npmjs.com/cli/v10/commands/npm-audit
- Locust: https://docs.locust.io/
- Apache JMeter: https://jmeter.apache.org/usermanual/component_reference.html
- Postman / newman: https://github.com/postmanlabs/newman
- python-ecdsa Minerva disclosure: https://github.com/tlsfuzzer/python-ecdsa/issues
- `PYSEC-2026-1805` (protobuf `ParseDict` DoS): https://github.com/protocolbuffers/protobuf/security/advisories
