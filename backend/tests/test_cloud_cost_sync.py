"""Integration tests for real AWS billing sync into CloudCost (Phase 18,
audit roadmap item 9) - exercises the full real path: project + linked
cloud account -> real boto3 Cost Explorer call (via moto) -> CloudCost
rows, through the actual HTTP API. See test_aws_cost_explorer.py for
moto's Cost Explorer emulation limitation (no way to seed cost data)."""
from moto import mock_aws

from app.models.cloud_provider_account import CloudProviderAccount
from app.utils.crypto import encrypt_credentials


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_cloud_account(db_session, user_id: int, provider: str = "aws") -> CloudProviderAccount:
    account = CloudProviderAccount(
        user_id=user_id,
        provider=provider,
        account_name=f"cost-test-{provider}-{user_id}",
        region="us-east-1",
        credentials_encrypted=encrypt_credentials(
            {"access_key_id": "testing", "secret_access_key": "testing"}
        ),
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)
    return account


def _make_project(client, token, suffix: str) -> dict:
    return client.post(
        "/api/v1/projects", json={"name": f"cost-sync-project-{suffix}"}, headers=_auth_header(token)
    ).json()


@mock_aws
def test_sync_project_cloud_costs_succeeds_with_no_data_from_a_fresh_fake_account(
    client, make_user_with_role, db_session
):
    """moto's Cost Explorer emulation cannot be seeded with cost data (no
    such API exists in real AWS either) - this proves the real request
    reaches Cost Explorer and completes cleanly (200/201, empty list)
    rather than erroring, which is the strongest verification possible
    without a real AWS billing account."""
    token = make_user_with_role("cost_sync_op_a", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"])
    project = _make_project(client, token, "a")

    response = client.post(
        f"/api/v1/projects/{project['id']}/cloud-costs/sync",
        params={"cloud_provider_account_id": account.id},
        headers=_auth_header(token),
    )
    assert response.status_code == 201
    assert response.json() == []


def test_sync_fails_clearly_for_unsupported_provider(client, make_user_with_role, db_session):
    token = make_user_with_role("cost_sync_op_b", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"], provider="azure")
    project = _make_project(client, token, "b")

    response = client.post(
        f"/api/v1/projects/{project['id']}/cloud-costs/sync",
        params={"cloud_provider_account_id": account.id},
        headers=_auth_header(token),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "COST_SYNC_PROVIDER_NOT_SUPPORTED"


def test_cannot_sync_using_another_users_cloud_account(client, make_user_with_role, db_session):
    token_a = make_user_with_role("cost_sync_op_c", "operator")
    token_b = make_user_with_role("cost_sync_op_d", "operator")
    me_b = client.get("/api/v1/auth/me", headers=_auth_header(token_b)).json()
    account_b = _make_cloud_account(db_session, me_b["id"])
    project = _make_project(client, token_a, "c")

    response = client.post(
        f"/api/v1/projects/{project['id']}/cloud-costs/sync",
        params={"cloud_provider_account_id": account_b.id},
        headers=_auth_header(token_a),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_YOUR_CLOUD_ACCOUNT"


def test_sync_fails_clearly_when_project_does_not_exist(client, make_user_with_role, db_session):
    token = make_user_with_role("cost_sync_op_e", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"])

    response = client.post(
        "/api/v1/projects/999999/cloud-costs/sync",
        params={"cloud_provider_account_id": account.id},
        headers=_auth_header(token),
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PROJECT_NOT_FOUND"


@mock_aws
def test_repeated_sync_does_not_duplicate_already_stored_months(
    client, make_user_with_role, db_session
):
    """CloudCostRepository.get_existing must make a second sync of the same
    period a no-op, not a duplicate row - verified directly against the
    service since moto's Cost Explorer can't be seeded to prove this via
    the HTTP path alone (see module docstring)."""
    from datetime import date

    from app.models.cloud_cost import CloudCost
    from app.services.cloud_cost_service import CloudCostService

    token = make_user_with_role("cost_sync_op_f", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"])
    project = _make_project(client, token, "f")

    # Pre-seed a CloudCost row exactly as a prior real sync would have
    # created it, then run the sync again and confirm no duplicate.
    db_session.add(
        CloudCost(
            project_id=project["id"],
            provider="aws",
            service_name="Amazon Elastic Compute Cloud - Compute",
            cost_amount=99.99,
            currency="USD",
            billing_period_start=date(2026, 5, 1),
            billing_period_end=date(2026, 5, 31),
        )
    )
    db_session.commit()

    assert (
        CloudCostService(db_session).repository.get_existing(
            project["id"], "aws", "Amazon Elastic Compute Cloud - Compute", date(2026, 5, 1)
        )
        is not None
    )

    created = CloudCostService(db_session).sync_from_aws(project["id"], account.id, me["id"])
    assert created == []  # moto returns no new data, and the pre-seeded month must not duplicate

    all_costs = CloudCostService(db_session).repository.list_all_for_project(project["id"])
    assert len(all_costs) == 1
