"""Unit tests for bcrypt password hashing utilities."""
from app.authentication.password_handler import hash_password, verify_password


def test_hash_password_produces_different_hash_each_time():
    hashed_a = hash_password("Sup3rSecret!")
    hashed_b = hash_password("Sup3rSecret!")
    assert hashed_a != hashed_b


def test_verify_password_succeeds_for_correct_password():
    hashed = hash_password("Sup3rSecret!")
    assert verify_password("Sup3rSecret!", hashed) is True


def test_verify_password_fails_for_incorrect_password():
    hashed = hash_password("Sup3rSecret!")
    assert verify_password("WrongPassword!", hashed) is False


def test_verify_password_handles_malformed_hash_gracefully():
    assert verify_password("anything", "not-a-real-hash") is False
