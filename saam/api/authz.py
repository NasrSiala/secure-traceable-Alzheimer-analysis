"""Matrice TRD §8–9 : aucune route applicative sans règle explicite."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, params
from fastapi.routing import APIRoute, iter_route_contexts

from saam.api.auth import current_user
from saam.identity.auth import AuthError, User
from saam.identity.seed import Role

ALL_ROLES: tuple[Role, ...] = ("operator", "auditor", "admin")
Policy = tuple[Role, ...] | Literal["public", "refresh"]
ROUTE_POLICIES: dict[tuple[str, str], Policy] = {
    ("GET", "/api/v1/health"): "public",
    ("POST", "/api/v1/auth/login"): "public",
    # Ces deux handlers authentifient le cookie opaque, sans exiger un JWT valide.
    ("POST", "/api/v1/auth/refresh"): "refresh",
    ("POST", "/api/v1/auth/logout"): "refresh",
    ("GET", "/api/v1/me"): ALL_ROLES,
    ("POST", "/api/v1/cases"): ("operator", "admin"),
    ("GET", "/api/v1/cases"): ALL_ROLES,
    ("GET", "/api/v1/cases/{case_id}"): ALL_ROLES,
    ("GET", "/api/v1/cases/{case_id}/signal"): ALL_ROLES,
    ("GET", "/api/v1/cases/{case_id}/history"): ALL_ROLES,
    ("GET", "/api/v1/cases/{case_id}/agent-logs"): ALL_ROLES,
    ("POST", "/api/v1/cases/{case_id}/verifications"): ALL_ROLES,
    ("GET", "/api/v1/cases/{case_id}/verifications"): ALL_ROLES,
    ("GET", "/api/v1/admin/users"): ("admin",),
    ("POST", "/api/v1/admin/users"): ("admin",),
    ("PATCH", "/api/v1/admin/users"): ("admin",),
}


def require_roles(*roles: Role) -> Callable[..., User]:
    """Le rôle vient de PostgreSQL via current_user, jamais d'un header/JWT."""
    if not roles or not set(roles) <= set(ALL_ROLES):
        raise ValueError("Au moins un rôle connu est obligatoire.")

    def authorize(user: Annotated[User, Depends(current_user)]) -> User:
        if user.role not in roles:
            raise AuthError(403, "FORBIDDEN", "Action non autorisée.")
        return user

    return authorize


class AuthorizedRoute(APIRoute):
    """Ajoute le contrôle avant le handler ; refuse les routes non déclarées."""

    def __init__(
        self,
        path: str,
        endpoint: Callable[..., Any],
        *,
        methods: list[str] | set[str] | None = None,
        dependencies: Sequence[params.Depends] | None = None,
        **kwargs: Any,
    ) -> None:
        guards = list(dependencies or ())
        policies = []
        for method in methods or {"GET"}:
            key = (method.upper(), path)
            if key not in ROUTE_POLICIES:
                raise ValueError(f"Route sans règle d'autorisation : {key}")
            policy = ROUTE_POLICIES[key]
            policies.append(policy)
            if isinstance(policy, tuple):
                guards.append(Depends(require_roles(*policy)))
        self.policies = tuple(policies)
        super().__init__(path, endpoint, methods=methods, dependencies=guards, **kwargs)


def assert_route_policies(app: FastAPI) -> None:
    """Détecte aussi un APIRouter ordinaire qui contournerait AuthorizedRoute."""
    for context in iter_route_contexts(app.routes):
        route = context.original_route
        if isinstance(route, APIRoute):
            if not isinstance(route, AuthorizedRoute):
                raise ValueError(f"Route sans contrôle d'autorisation : {route.path}")
            if any(
                ROUTE_POLICIES.get((method, context.path or ""))
                != ROUTE_POLICIES.get((method, route.path))
                for method in route.methods or ()
            ):
                raise ValueError(f"Préfixe sans règle d'autorisation : {context.path}")
        elif context.path != app.openapi_url:
            raise ValueError("Route non applicative non déclarée.")
