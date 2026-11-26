"""Authentification HTTP, sessions, refus et concurrence sur PostgreSQL réel."""

import time
from concurrent.futures import ThreadPoolExecutor

import jwt
import psycopg
import pytest
from fastapi.testclient import TestClient

from saam.api.auth import COOKIE
from saam.api.main import create_app
from saam.identity.auth import AUDIENCE, ISSUER, AuthError, IdentityService, token_hash
from tests.api.conftest import PASSWORD


def login(client, role="operator", password=PASSWORD):
    return client.post(
        "/api/v1/auth/login", json={"email": f"{role}@demo.test", "password": password}
    )


@pytest.mark.parametrize("role", ["admin", "operator", "auditor"])
def test_login_cookie_jwt_and_profile(
    auth_client, auth_service, postgres, migrated_database, role
) -> None:
    response = login(auth_client, role)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["role"] == role and body["expires_in"] == 1800
    assert "password_hash" not in body["user"] and "refresh_token" not in body
    cookie = response.headers["set-cookie"].lower()
    assert all(
        flag in cookie
        for flag in ("httponly", "secure", "samesite=strict", "path=/api/v1/auth")
    )
    refresh = auth_client.cookies.get(COOKIE)
    claims = jwt.decode(
        body["access_token"],
        auth_service.jwt_secret,
        algorithms=["HS256"],
        issuer=ISSUER,
        audience=AUDIENCE,
    )
    assert claims["exp"] - claims["iat"] == 1800
    profile = auth_client.get(
        "/api/v1/me", headers={"Authorization": "Bearer " + body["access_token"]}
    )
    assert profile.json() == body["user"]
    with psycopg.connect(postgres.dsn(migrated_database)) as connection:
        row = connection.execute(
            "SELECT token_hash, extract(epoch FROM expires_at-created_at) FROM refresh_tokens"
        ).fetchone()
        assert row[0] == token_hash(refresh) and row[0] != refresh
        assert 28790 <= float(row[1]) <= 28800


def test_invalid_credentials_have_one_message_and_are_recorded(
    auth_client, postgres, migrated_database
) -> None:
    wrong = login(auth_client, password="incorrect")
    unknown = auth_client.post(
        "/api/v1/auth/login", json={"email": "unknown@demo.test", "password": PASSWORD}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.json()["error"]["message"] == "E-mail ou mot de passe incorrect."
    with psycopg.connect(postgres.dsn(migrated_database)) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM login_attempts WHERE NOT succeeded"
            ).fetchone()[0]
            == 2
        )


def test_five_failures_lock_the_sixth_and_survive_http_errors(
    auth_client, postgres, migrated_database
) -> None:
    for _ in range(5):
        assert login(auth_client, password="incorrect").status_code == 401
    blocked = login(auth_client)
    assert blocked.status_code == 423
    assert (
        blocked.json()["error"]["message"]
        == "Trop de tentatives. Réessayez dans 15 minutes."
    )
    with psycopg.connect(postgres.dsn(migrated_database)) as connection:
        seconds = connection.execute(
            "SELECT extract(epoch FROM locked_until-now()) FROM users WHERE role='operator'"
        ).fetchone()[0]
        assert 880 < seconds <= 900
        connection.execute(
            "UPDATE users SET locked_until=now()-interval '1 second' WHERE role='operator'"
        )
        connection.execute(
            "UPDATE login_attempts SET attempted_at=now()-interval '16 minutes'"
        )
    assert login(auth_client).status_code == 200


def test_disabled_account_requires_correct_password(
    auth_client, postgres, migrated_database
) -> None:
    with psycopg.connect(postgres.dsn(migrated_database)) as connection:
        connection.execute("UPDATE users SET is_active=false WHERE role='operator'")
    assert login(auth_client, password="incorrect").status_code == 401
    assert login(auth_client).status_code == 403


def test_rate_limit_is_shared_by_service_instances(auth_service) -> None:
    second = IdentityService(auth_service.database_url, auth_service.jwt_secret)
    for index in range(10):
        (auth_service if index % 2 else second).login(
            "operator@demo.test", PASSWORD, "127.0.0.5"
        )
    with pytest.raises(AuthError) as error:
        second.login("operator@demo.test", PASSWORD, "127.0.0.5")
    assert error.value.status == 429
    assert (
        second.login("operator@demo.test", PASSWORD, "127.0.0.6").user.role
        == "operator"
    )


def test_refresh_rotates_once_without_extending_eight_hours(
    auth_client, auth_service, postgres, migrated_database
) -> None:
    assert login(auth_client).status_code == 200
    old = auth_client.cookies.get(COOKIE)
    response = auth_client.post("/api/v1/auth/refresh")
    assert response.status_code == 200
    assert auth_client.cookies.get(COOKIE) != old
    with pytest.raises(AuthError) as error:
        auth_service.refresh(old)
    assert error.value.status == 401
    with psycopg.connect(postgres.dsn(migrated_database)) as connection:
        rows = connection.execute(
            "SELECT expires_at, revoked_at FROM refresh_tokens ORDER BY created_at"
        ).fetchall()
        assert rows[0][0] == rows[1][0]
        assert rows[0][1] is not None and rows[1][1] is None


def test_concurrent_refresh_has_one_winner(auth_client, auth_service) -> None:
    login(auth_client)
    old = auth_client.cookies.get(COOKIE)

    def rotate():
        try:
            auth_service.refresh(old)
            return 200
        except AuthError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: rotate(), range(2)))
    assert sorted(outcomes) == [200, 401]


def test_logout_revokes_refresh_and_clears_cookie(auth_client, auth_service) -> None:
    login(auth_client)
    old = auth_client.cookies.get(COOKIE)
    response = auth_client.post("/api/v1/auth/logout")
    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert auth_client.cookies.get(COOKIE) is None
    with pytest.raises(AuthError) as error:
        auth_service.refresh(old)
    assert error.value.status == 401


@pytest.mark.parametrize(
    "kind", ["expired", "signature", "audience", "issuer", "type", "algorithm"]
)
def test_invalid_access_tokens_are_rejected(auth_client, auth_service, kind) -> None:
    token = login(auth_client).json()["access_token"]
    claims = jwt.decode(token, options={"verify_signature": False})
    secret = auth_service.jwt_secret
    if kind == "expired":
        claims["exp"] = int(time.time()) - 1
    if kind == "signature":
        secret = "different-secret-" * 4
    if kind == "audience":
        claims["aud"] = "other"
    if kind == "issuer":
        claims["iss"] = "other"
    if kind == "type":
        claims["type"] = "refresh"
    invalid = (
        jwt.encode(claims, None, algorithm="none")
        if kind == "algorithm"
        else jwt.encode(claims, secret, algorithm="HS256")
    )
    assert (
        auth_client.get(
            "/api/v1/me", headers={"Authorization": "Bearer " + invalid}
        ).status_code
        == 401
    )


@pytest.mark.parametrize(
    "path", ["/api/v1/me", "/api/v1/auth/refresh", "/api/v1/auth/logout"]
)
def test_session_required(auth_client, path) -> None:
    response = auth_client.get(path) if path.endswith("/me") else auth_client.post(path)
    assert response.status_code == 401


def test_expired_refresh_and_disabled_user_are_rejected(
    auth_client, auth_service, postgres, migrated_database
) -> None:
    login(auth_client)
    old = auth_client.cookies.get(COOKIE)
    with psycopg.connect(postgres.dsn(migrated_database)) as connection:
        connection.execute(
            "UPDATE refresh_tokens SET created_at=now()-interval '9 hours', expires_at=now()-interval '1 hour'"
        )
    with pytest.raises(AuthError) as error:
        auth_service.refresh(old)
    assert error.value.status == 401
    login(auth_client)
    token = auth_client.cookies.get(COOKIE)
    with psycopg.connect(postgres.dsn(migrated_database)) as connection:
        connection.execute("UPDATE users SET is_active=false WHERE role='operator'")
    with pytest.raises(AuthError) as disabled:
        auth_service.refresh(token)
    assert disabled.value.status == 403


def test_profile_uses_current_database_role(
    auth_client, postgres, migrated_database
) -> None:
    token = login(auth_client, "admin").json()["access_token"]
    with psycopg.connect(postgres.dsn(migrated_database)) as connection:
        connection.execute(
            "UPDATE users SET role='auditor' WHERE email='admin@demo.test'"
        )
    assert (
        auth_client.get(
            "/api/v1/me", headers={"Authorization": "Bearer " + token}
        ).json()["role"]
        == "auditor"
    )


@pytest.mark.parametrize(
    "body",
    [
        {"email": "invalid", "password": "private-submitted-value"},
        {"email": "operator@demo.test"},
        {
            "email": "operator@demo.test",
            "password": "private-submitted-value",
            "role": "admin",
        },
    ],
)
def test_validation_does_not_echo_credentials(auth_client, body) -> None:
    response = auth_client.post("/api/v1/auth/login", json=body)
    assert response.status_code == 400
    assert "private-submitted-value" not in response.text


@pytest.mark.parametrize("action", ["login", "refresh", "logout"])
def test_cross_origin_requests_do_not_modify_session(
    auth_client, auth_service, action
) -> None:
    login(auth_client)
    old = auth_client.cookies.get(COOKIE)
    body = (
        {"email": "operator@demo.test", "password": PASSWORD}
        if action == "login"
        else None
    )
    response = auth_client.post(
        "/api/v1/auth/" + action, json=body, headers={"Origin": "https://evil.test"}
    )
    assert response.status_code == 403
    assert auth_service.refresh(old).user.role == "operator"


def test_weak_configuration_is_unavailable_without_secret_details(auth_service) -> None:
    with TestClient(
        create_app(identity=IdentityService(auth_service.database_url, "")),
        base_url="https://testserver",
        client=("127.0.0.1", 50000),
    ) as client:
        response = login(client)
        assert response.status_code == 503
        assert auth_service.database_url not in response.text


def test_openapi_exposes_the_session_contract(auth_client) -> None:
    schema = auth_client.get("/api/v1/openapi.json").json()
    assert set(schema["components"]["schemas"]["SessionResponse"]["properties"]) == {
        "access_token",
        "token_type",
        "expires_in",
        "user",
    }
    assert (
        "password_hash"
        not in schema["components"]["schemas"]["UserResponse"]["properties"]
    )


def test_http_rate_limit_cannot_be_bypassed_with_forwarded_header(auth_client) -> None:
    for index in range(10):
        response = auth_client.post(
            "/api/v1/auth/login",
            json={"email": f"unknown{index}@demo.test", "password": PASSWORD},
            headers={"X-Forwarded-For": f"192.0.2.{index + 1}"},
        )
        assert response.status_code == 401
    limited = login(auth_client)
    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"
