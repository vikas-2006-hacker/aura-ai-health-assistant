from app.utils.security import hash_password, verify_password
from app.services.auth_service import create_access_token, decode_access_token
from app.core.config import settings
import time


def test_password_hash_and_verify() -> None:
    pwd = "MyS3cretPass!"
    h = hash_password(pwd)
    assert h != pwd
    assert verify_password(pwd, h)
    assert not verify_password("wrong", h)


def test_jwt_create_and_decode() -> None:
    token = create_access_token({"sub": "123"}, expires_delta=1)
    payload = decode_access_token(token)
    assert payload.get("sub") == "123"


def test_jwt_expiry() -> None:
    token = create_access_token({"sub": "321"}, expires_delta=-1)
    # token should be immediately expired; decode should raise HTTPException
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        decode_access_token(token)
