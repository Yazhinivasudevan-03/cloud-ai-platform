"""Integration tests for Phase 25's dynamic region discovery: the real
GET/refresh/PATCH endpoints, CloudRegionSyncService's new-region diffing
and notification dispatch, and sync_all_regions()'s per-account tolerance -
verified against moto's real EC2 emulation (the same faithful boto3 request
path test_cloud_sync.py already relies on for CloudWatch)."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from moto import mock_aws

from app.config.settings import get_settings
from app.models.alert import Alert
from app.models.cloud_provider_account import CloudProviderAccount
from app.models.notification import Notification
from app.services.cloud_region_sync_service import CloudRegionSyncService
from app.utils.crypto import encrypt_credentials


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_cloud_account(db_session, user_id: int, suffix: str) -> CloudProviderAccount:
    account = CloudProviderAccount(
        user_id=user_id,
        provider="aws",
        account_name=f"region-test-{suffix}",
        region="us-east-1",
        credentials_encrypted=encrypt_credentials({"access_key_id": "testing", "secret_access_key": "testing"}),
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)
    return account


@mock_aws
def test_get_regions_triggers_a_live_sync_the_first_time(client, make_user_with_role, db_session):
    token = make_user_with_role("region_op_a", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"], "a")

    response = client.get(f"/api/v1/cloud-provider-accounts/{account.id}/regions", headers=_auth_header(token))

    assert response.status_code == 200
    body = response.json()
    assert body["connection_status"] == "CONNECTED"
    assert body["last_region_sync"] is not None
    region_ids = {r["id"] for r in body["regions"]}
    assert "us-east-1" in region_ids
    assert body["selected_region"] == "us-east-1"


@mock_aws
def test_get_regions_serves_the_cached_snapshot_on_a_second_call(client, make_user_with_role, db_session):
    token = make_user_with_role("region_op_b", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"], "b")

    first = client.get(f"/api/v1/cloud-provider-accounts/{account.id}/regions", headers=_auth_header(token)).json()
    second = client.get(f"/api/v1/cloud-provider-accounts/{account.id}/regions", headers=_auth_header(token)).json()

    # A second read of an already-synced account must not trigger another
    # live call - last_region_sync (and the region snapshot) stays exactly
    # what the first sync produced.
    assert second["last_region_sync"] == first["last_region_sync"]
    assert second["regions"] == first["regions"]


@mock_aws
def test_get_regions_triggers_a_live_sync_once_the_cache_ttl_expires(client, make_user_with_role, db_session):
    # Phase 25E: CLOUD_REGION_CACHE_TTL_HOURS bounds how stale a served
    # region snapshot can ever be - a last_region_sync older than the TTL
    # must trigger a fresh live call, exactly like a never-synced account.
    token = make_user_with_role("region_op_ttl", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"], "ttl")

    client.get(f"/api/v1/cloud-provider-accounts/{account.id}/regions", headers=_auth_header(token))

    ttl_hours = get_settings().CLOUD_REGION_CACHE_TTL_HOURS
    stale_sync_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=ttl_hours + 1)
    db_session.query(CloudProviderAccount).filter(CloudProviderAccount.id == account.id).update(
        {"last_region_sync": stale_sync_time}
    )
    db_session.commit()

    second = client.get(f"/api/v1/cloud-provider-accounts/{account.id}/regions", headers=_auth_header(token)).json()

    # A real resync must have replaced the stale timestamp with a recent
    # one - compared against the known artificial past value (not the
    # first call's timestamp) so this doesn't depend on the two live calls
    # landing in different seconds under MySQL's DATETIME's whole-second
    # precision.
    returned = datetime.fromisoformat(second["last_region_sync"])
    assert (returned - stale_sync_time).total_seconds() > 3600


@mock_aws
def test_get_regions_does_not_resync_within_the_cache_ttl(client, make_user_with_role, db_session):
    token = make_user_with_role("region_op_fresh", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"], "fresh")

    client.get(f"/api/v1/cloud-provider-accounts/{account.id}/regions", headers=_auth_header(token))

    ttl_hours = get_settings().CLOUD_REGION_CACHE_TTL_HOURS
    still_fresh_sync_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=ttl_hours - 1)
    db_session.query(CloudProviderAccount).filter(CloudProviderAccount.id == account.id).update(
        {"last_region_sync": still_fresh_sync_time}
    )
    db_session.commit()

    second = client.get(f"/api/v1/cloud-provider-accounts/{account.id}/regions", headers=_auth_header(token)).json()

    # Still within the TTL window - last_region_sync must be served as
    # stored (MySQL's DATETIME column truncates microseconds, so compare
    # with a small tolerance rather than exact string equality), not
    # overwritten by a fresh live call.
    returned = datetime.fromisoformat(second["last_region_sync"])
    assert abs((returned - still_fresh_sync_time).total_seconds()) < 2


@mock_aws
def test_refresh_regions_always_forces_a_live_call(client, make_user_with_role, db_session):
    token = make_user_with_role("region_op_c", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"], "c")

    response = client.post(
        f"/api/v1/cloud-provider-accounts/{account.id}/refresh-regions", headers=_auth_header(token)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["connection_status"] == "CONNECTED"
    assert len(body["regions"]) > 0


@mock_aws
def test_update_region_accepts_a_discovered_region_and_the_all_sentinel(
    client, make_user_with_role, db_session
):
    token = make_user_with_role("region_op_d", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"], "d")
    client.get(f"/api/v1/cloud-provider-accounts/{account.id}/regions", headers=_auth_header(token))

    switch_to_all = client.patch(
        f"/api/v1/cloud-provider-accounts/{account.id}/region",
        json={"selected_region": "all"},
        headers=_auth_header(token),
    )
    assert switch_to_all.status_code == 200
    assert switch_to_all.json()["region"] == "all"

    switch_to_real_region = client.patch(
        f"/api/v1/cloud-provider-accounts/{account.id}/region",
        json={"selected_region": "eu-west-2"},
        headers=_auth_header(token),
    )
    assert switch_to_real_region.status_code == 200
    assert switch_to_real_region.json()["region"] == "eu-west-2"


@mock_aws
def test_update_region_rejects_a_region_that_was_never_discovered(client, make_user_with_role, db_session):
    token = make_user_with_role("region_op_e", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"], "e")
    client.get(f"/api/v1/cloud-provider-accounts/{account.id}/regions", headers=_auth_header(token))

    response = client.patch(
        f"/api/v1/cloud-provider-accounts/{account.id}/region",
        json={"selected_region": "mars-central-1"},
        headers=_auth_header(token),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REGION_NOT_AVAILABLE"


@mock_aws
@pytest.mark.parametrize(
    "endpoint,method",
    [
        ("regions", "get"),
        ("refresh-regions", "post"),
    ],
)
def test_region_endpoints_reject_a_non_owner(client, make_user_with_role, db_session, endpoint, method):
    owner_token = make_user_with_role("region_owner_f", "operator")
    other_token = make_user_with_role("region_other_f", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(owner_token)).json()
    account = _make_cloud_account(db_session, me["id"], "f")

    response = getattr(client, method)(
        f"/api/v1/cloud-provider-accounts/{account.id}/{endpoint}", headers=_auth_header(other_token)
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_YOUR_CLOUD_ACCOUNT"


@mock_aws
def test_update_region_rejects_a_non_owner(client, make_user_with_role, db_session):
    owner_token = make_user_with_role("region_owner_g", "operator")
    other_token = make_user_with_role("region_other_g", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(owner_token)).json()
    account = _make_cloud_account(db_session, me["id"], "g")

    response = client.patch(
        f"/api/v1/cloud-provider-accounts/{account.id}/region",
        json={"selected_region": "all"},
        headers=_auth_header(other_token),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_YOUR_CLOUD_ACCOUNT"


@mock_aws
def test_sync_account_notifies_the_owner_when_new_regions_appear(client, make_user_with_role, db_session):
    token = make_user_with_role("region_op_h", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"], "h")
    # Simulate a prior baseline narrower than what AWS actually has (moto's
    # describe_regions returns the full real region set every time) - the
    # next real sync will genuinely discover "new" regions relative to it.
    account.available_regions = json.dumps([{"id": "us-east-1", "display_name": "US East (N. Virginia)"}])
    db_session.commit()

    result = CloudRegionSyncService(db_session).sync_account(account.id)

    assert len(result.new_region_ids) > 0

    alerts = (
        db_session.query(Alert)
        .filter(Alert.user_id == me["id"], Alert.alert_type == "new_cloud_regions_available")
        .all()
    )
    assert len(alerts) == 1
    assert alerts[0].severity == "info"

    notifications = db_session.query(Notification).filter(Notification.alert_id == alerts[0].id).all()
    assert any(n.user_id == me["id"] for n in notifications)


@mock_aws
def test_sync_account_does_not_notify_on_the_very_first_sync(client, make_user_with_role, db_session):
    token = make_user_with_role("region_op_i", "operator")
    me = client.get("/api/v1/auth/me", headers=_auth_header(token)).json()
    account = _make_cloud_account(db_session, me["id"], "i")

    CloudRegionSyncService(db_session).sync_account(account.id)

    alerts = (
        db_session.query(Alert)
        .filter(Alert.user_id == me["id"], Alert.alert_type == "new_cloud_regions_available")
        .all()
    )
    assert alerts == []


def test_sync_all_regions_tolerates_an_unsupported_provider(client, make_user_with_role, db_session):
    token_a = make_user_with_role("region_op_j", "operator")
    token_b = make_user_with_role("region_op_k", "operator")
    me_a = client.get("/api/v1/auth/me", headers=_auth_header(token_a)).json()
    me_b = client.get("/api/v1/auth/me", headers=_auth_header(token_b)).json()

    good_account = _make_cloud_account(db_session, me_a["id"], "j")
    bad_account = CloudProviderAccount(
        user_id=me_b["id"],
        provider="not_a_real_provider",
        account_name="region-test-broken",
        region="nowhere-1",
        credentials_encrypted=encrypt_credentials({"anything": "goes"}),
    )
    db_session.add(bad_account)
    db_session.commit()

    with mock_aws():
        summary = CloudRegionSyncService(db_session).sync_all_regions()

    assert summary.accounts_attempted == 2
    assert summary.accounts_synced == 1
    assert summary.accounts_failed == 1

    db_session.refresh(good_account)
    db_session.refresh(bad_account)
    assert good_account.connection_status == "CONNECTED"
    assert bad_account.connection_status == "ERROR"
