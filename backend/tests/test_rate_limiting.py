"""Tests confirming rate limiting was genuinely broadened beyond login/
register (see docs/PHASE_18.md) - previously every other endpoint,
including expensive ones, was completely unthrottled. Follows the exact
same boundary-testing convention as test_auth.py::test_register_is_rate_limited:
send exactly the configured limit's worth of requests (all must succeed),
then one more (must be rejected with 429).

The two highest-limit endpoints (RATE_LIMIT_CLOUD_SYNC=30/hour and
RATE_LIMIT_INGESTION=120/minute) are deliberately not boundary-tested here -
a 121-request unit test would be real but disproportionately slow. Their
decorator wiring is still exercised by every other test that calls them
successfully (test_cloud_sync.py, test_metrics.py) after this change.
"""
def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_alerts_evaluate_is_rate_limited(client, make_user_with_role):
    token = make_user_with_role("rl_alerts_op", "operator")

    for _ in range(10):
        response = client.post("/api/v1/alerts/evaluate", headers=_auth_header(token))
        assert response.status_code == 200

    response = client.post("/api/v1/alerts/evaluate", headers=_auth_header(token))
    assert response.status_code == 429


def test_optimization_evaluate_is_rate_limited(client, make_user_with_role):
    token = make_user_with_role("rl_opt_op", "operator")

    for _ in range(10):
        response = client.post("/api/v1/optimization/evaluate", headers=_auth_header(token))
        assert response.status_code == 200

    response = client.post("/api/v1/optimization/evaluate", headers=_auth_header(token))
    assert response.status_code == 429


def test_auth_refresh_is_rate_limited(client):
    # An invalid token still reaches (and is counted by) the rate limiter -
    # the limiter check happens before the handler's own token validation,
    # so this exercises the same boundary without needing a real session.
    for _ in range(20):
        response = client.post("/api/v1/auth/refresh", params={"refresh_token": "not-a-real-token"})
        assert response.status_code == 401

    response = client.post("/api/v1/auth/refresh", params={"refresh_token": "not-a-real-token"})
    assert response.status_code == 429
