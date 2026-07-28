"""Integration tests for the global RequestValidationError handler
(app/middleware/error_handler.py) - previously returned a hardcoded,
unhelpful "Request validation failed" message on every 422 regardless of
what actually failed, hiding the real per-field Pydantic errors in an
unread `details` array. These tests exercise it through the real
POST /auth/register endpoint (rather than unit-testing the handler in
isolation) to prove the fix end-to-end, the same way the frontend
actually consumes it."""


def test_missing_field_produces_a_specific_message_not_the_generic_one(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "mobile_number": "+14155552671",
            "country": "GB",
            "password": "Sup3rSecret1",
            "confirm_password": "Sup3rSecret1",
            # email deliberately omitted
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["message"] == "Missing required field: email"
    assert body["error"]["message"] != "Request validation failed"

    detail = body["error"]["details"][0]
    assert detail["loc"] == ["body", "email"]
    assert detail["type"] == "missing"


def test_invalid_phone_format_produces_the_real_field_validator_message(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "error-handler-phone@example.com",
            "mobile_number": "(415) 555-2671",  # not E.164
            "country": "GB",
            "password": "Sup3rSecret1",
            "confirm_password": "Sup3rSecret1",
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["message"] == "mobile_number must be in E.164 format, e.g. +14155552671"
    # The raw Pydantic "Value error, " prefix must never leak to the client.
    assert not body["error"]["message"].startswith("Value error")

    detail = body["error"]["details"][0]
    assert detail["loc"] == ["body", "mobile_number"]


def test_weak_password_produces_the_real_field_validator_message(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "error-handler-weakpw@example.com",
            "mobile_number": "+14155552671",
            "country": "GB",
            "password": "weakpass",
            "confirm_password": "weakpass",
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["message"] == "password must contain at least one uppercase letter"


def test_mismatched_confirm_password_produces_a_real_model_level_message(client):
    """A model_validator(mode="after") error (no single field in `loc`)
    must still surface its real message, not the generic placeholder."""
    response = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "error-handler-mismatch@example.com",
            "mobile_number": "+14155552671",
            "country": "GB",
            "password": "Sup3rSecret1",
            "confirm_password": "Different1",
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["message"] == "password and confirm_password must match"

    detail = body["error"]["details"][0]
    assert detail["loc"] == ["body"]  # no single field - a cross-field check


def test_multiple_simultaneous_errors_are_all_included(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "first_name": "Ada",
            "last_name": "Lovelace",
            "mobile_number": "not-a-phone",
            "country": "GB",
            "password": "weakpass",
            "confirm_password": "weakpass",
            # email also omitted
        },
    )
    assert response.status_code == 422
    body = response.json()
    assert "Missing required field: email" in body["error"]["message"]
    assert "E.164 format" in body["error"]["message"]
    assert "uppercase letter" in body["error"]["message"]
    assert len(body["error"]["details"]) == 3
