"""Chaque case de la matrice, et absence de contournement sur l'API réelle."""

import psycopg
import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from saam.api.auth import current_user
from saam.api.authz import (
    ALL_ROLES,
    ROUTE_POLICIES,
    AuthorizedRoute,
    assert_route_policies,
    require_roles,
)
from saam.api.main import create_app
from saam.identity.auth import IdentityService, User
from tests.api.conftest import PASSWORD

# Valeurs attendues indépendantes, tirées de TRD §8.1 et §9.
MATRIX = [
    ("GET", "/me", ALL_ROLES),
    ("POST", "/cases", ("operator", "admin")),
    ("GET", "/cases", ALL_ROLES),
    ("GET", "/cases/{case_id}", ALL_ROLES),
    ("GET", "/cases/{case_id}/signal", ALL_ROLES),
    ("GET", "/cases/{case_id}/history", ALL_ROLES),
    ("GET", "/cases/{case_id}/agent-logs", ALL_ROLES),
    ("POST", "/cases/{case_id}/verifications", ALL_ROLES),
    ("GET", "/cases/{case_id}/verifications", ALL_ROLES),
    ("GET", "/admin/users", ("admin",)),
    ("POST", "/admin/users", ("admin",)),
    ("PATCH", "/admin/users", ("admin",)),
]


def matrix_app(service):
    app = create_app(identity=service)
    for method, path, _ in MATRIX:
        if path != "/me":
            # Handlers de test seulement ; les fonctions métier restent aux T3/T4.
            app.add_api_route("/api/v1" + path, lambda: {"ok": True}, methods=[method])
    return app


@pytest.mark.parametrize("role", ALL_ROLES)
@pytest.mark.parametrize("method,path,allowed", MATRIX)
def test_every_matrix_cell(method, path, allowed, role) -> None:
    app = matrix_app(IdentityService("", ""))
    user = User("test", "synthetic@demo.test", "Démo", role)
    app.dependency_overrides[current_user] = lambda: user
    with TestClient(app) as client:
        response = client.request(method, "/api/v1" + path.replace("{case_id}", "case"))
    assert response.status_code == (200 if role in allowed else 403)
    if role not in allowed:
        assert response.json()["error"] == {
            "code": "FORBIDDEN",
            "message": "Action non autorisée.",
            "details": {},
        }


@pytest.mark.parametrize("role", ALL_ROLES)
def test_real_jwt_database_role_and_anonymous_matrix(auth_service, role) -> None:
    app = matrix_app(auth_service)
    with TestClient(
        app, base_url="https://testserver", client=("127.0.0.1", 50000)
    ) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": f"{role}@demo.test", "password": PASSWORD},
        )
        token = response.json()["access_token"]
        for method, path, allowed in MATRIX:
            url = "/api/v1" + path.replace("{case_id}", "case")
            assert client.request(method, url).status_code == 401
            result = client.request(
                method,
                url,
                headers={"Authorization": "Bearer " + token, "X-Role": "admin"},
            )
            assert result.status_code == (200 if role in allowed else 403), url


def test_demoted_and_disabled_admin_cannot_use_old_token(auth_service) -> None:
    with TestClient(
        matrix_app(auth_service),
        base_url="https://testserver",
        client=("127.0.0.1", 50000),
    ) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@demo.test", "password": PASSWORD},
        )
        headers = {"Authorization": "Bearer " + login.json()["access_token"]}
        assert client.get("/api/v1/admin/users", headers=headers).status_code == 200
        with psycopg.connect(auth_service.database_url) as connection:
            connection.execute(
                "UPDATE users SET role='auditor' WHERE email='admin@demo.test'"
            )
        assert client.get("/api/v1/admin/users", headers=headers).status_code == 403
        with psycopg.connect(auth_service.database_url) as connection:
            connection.execute(
                "UPDATE users SET is_active=false WHERE email='admin@demo.test'"
            )
        assert client.get("/api/v1/cases", headers=headers).status_code == 403


def test_production_routes_all_have_policy_and_public_exceptions() -> None:
    app = create_app()
    assert_route_policies(app)
    assert set(ROUTE_POLICIES) == {
        (method, "/api/v1" + path) for method, path, _ in MATRIX
    } | {
        ("GET", "/api/v1/health"),
        ("POST", "/api/v1/auth/login"),
        ("POST", "/api/v1/auth/refresh"),
        ("POST", "/api/v1/auth/logout"),
    }
    for method, path, allowed in MATRIX:
        assert ROUTE_POLICIES[(method, "/api/v1" + path)] == allowed
    schema = app.openapi()
    assert schema["paths"]["/api/v1/me"]["get"]["security"] == [{"HTTPBearer": []}]
    assert "security" not in schema["paths"]["/api/v1/auth/refresh"]["post"]


def test_new_route_without_rule_is_rejected() -> None:
    app = create_app()
    with pytest.raises(ValueError, match="sans règle"):
        app.add_api_route("/api/v1/unprotected", lambda: None)
    router = APIRouter()
    router.add_api_route("/api/v1/cases", lambda: None)
    app.include_router(router)
    with pytest.raises(ValueError, match="sans contrôle"):
        assert_route_policies(app)


def test_invalid_role_policy_is_rejected() -> None:
    with pytest.raises(ValueError):
        require_roles()
    with pytest.raises(ValueError):
        require_roles("unknown")


def test_auth_router_cannot_leave_unknown_route_unprotected() -> None:
    with pytest.raises(ValueError, match="sans règle"):
        AuthorizedRoute("/api/v1/new", lambda: None, methods=["POST"])
