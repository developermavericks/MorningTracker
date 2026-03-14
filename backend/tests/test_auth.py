from routers.auth_utils import create_access_token, jwt, SECRET_KEY, ALGORITHM

def test_create_access_token():
    data = {"sub": "test@example.com", "user_id": "test_123"}
    token = create_access_token(data)
    assert token is not None
    
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert payload.get("sub") == "test@example.com"
    assert payload.get("user_id") == "test_123"
    assert "exp" in payload

def test_token_expiration():
    # Token expiration is handled by jose/jwt, we just verify the 'exp' field exists
    data = {"sub": "test@example.com", "user_id": "test_123"}
    token = create_access_token(data)
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert payload.get("exp") > 0
