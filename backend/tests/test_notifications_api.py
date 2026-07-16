"""Integration tests for the self-service Notification REST API."""
from app.models.notification import Notification


def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _get_user_id(client, token: str) -> int:
    return client.get("/api/v1/auth/me", headers=_auth_header(token)).json()["id"]


def test_list_my_notifications_only_returns_own(client, make_user_with_role, db_session):
    token_a = make_user_with_role("user_a")
    token_b = make_user_with_role("user_b")
    user_a_id = _get_user_id(client, token_a)
    user_b_id = _get_user_id(client, token_b)

    db_session.add_all(
        [
            Notification(user_id=user_a_id, channel="dashboard", message="for A", is_read=False),
            Notification(user_id=user_b_id, channel="dashboard", message="for B", is_read=False),
        ]
    )
    db_session.commit()

    response = client.get("/api/v1/notifications", headers=_auth_header(token_a))
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 1
    assert body["items"][0]["message"] == "for A"


def test_filter_notifications_by_is_read(client, make_user_with_role, db_session):
    token = make_user_with_role("user_c")
    user_id = _get_user_id(client, token)

    db_session.add_all(
        [
            Notification(user_id=user_id, channel="dashboard", message="read one", is_read=True),
            Notification(user_id=user_id, channel="dashboard", message="unread one", is_read=False),
        ]
    )
    db_session.commit()

    response = client.get(
        "/api/v1/notifications", params={"is_read": "false"}, headers=_auth_header(token)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["total"] == 1
    assert body["items"][0]["message"] == "unread one"


def test_mark_notification_read(client, make_user_with_role, db_session):
    token = make_user_with_role("user_d")
    user_id = _get_user_id(client, token)

    notification = Notification(user_id=user_id, channel="dashboard", message="hi", is_read=False)
    db_session.add(notification)
    db_session.commit()
    db_session.refresh(notification)

    response = client.patch(
        f"/api/v1/notifications/{notification.id}/read", headers=_auth_header(token)
    )
    assert response.status_code == 200
    assert response.json()["is_read"] is True


def test_cannot_mark_another_users_notification_read(client, make_user_with_role, db_session):
    token_a = make_user_with_role("user_e")
    token_b = make_user_with_role("user_f")
    user_a_id = _get_user_id(client, token_a)

    notification = Notification(user_id=user_a_id, channel="dashboard", message="hi", is_read=False)
    db_session.add(notification)
    db_session.commit()
    db_session.refresh(notification)

    response = client.patch(
        f"/api/v1/notifications/{notification.id}/read", headers=_auth_header(token_b)
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "NOT_YOUR_NOTIFICATION"


def test_mark_nonexistent_notification_read_returns_404(client, make_user_with_role):
    token = make_user_with_role("user_g")
    response = client.patch("/api/v1/notifications/999999/read", headers=_auth_header(token))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOTIFICATION_NOT_FOUND"
