"""Contrat HTTP d'authentification ; les secrets de refresh restent en cookie."""

from __future__ import annotations

import os
import re
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated, Literal

import psycopg
from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from saam.identity.auth import AuthError, IdentityService, Session, User
from saam.identity.seed import Role

COOKIE = "saam_refresh"
COOKIE_PATH = "/api/v1/auth"
BEARER = HTTPBearer(auto_error=False)


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str
    role: Role


class SessionResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"]
    expires_in: int
    user: UserResponse


class LoginInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("email")
    @classmethod
    def email_format(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Adresse e-mail invalide.")
        return value


def current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(BEARER)],
) -> User:
    if credentials is None:
        raise AuthError(401, "UNAUTHENTICATED", "Session expirée. Reconnectez-vous.")
    service: IdentityService = request.app.state.identity
    return service.profile(credentials.credentials)


def error_response(error: AuthError) -> JSONResponse:
    headers = {"Cache-Control": "no-store"}
    if error.status == 401:
        headers["WWW-Authenticate"] = "Bearer"
    if error.status in {423, 429}:
        headers["Retry-After"] = "900" if error.status == 423 else "60"
    return JSONResponse(
        status_code=error.status,
        headers=headers,
        content={
            "error": {"code": error.code, "message": error.message, "details": {}}
        },
    )


def session_response(session: Session) -> JSONResponse:
    response = JSONResponse(
        content={
            "access_token": session.access_token,
            "token_type": "bearer",
            "expires_in": 1800,
            "user": asdict(session.user),
        },
        headers={"Cache-Control": "no-store"},
    )
    response.set_cookie(
        COOKIE,
        session.refresh_token,
        httponly=True,
        secure=True,
        samesite="strict",
        path=COOKIE_PATH,
        max_age=max(0, int((session.expires_at - datetime.now(UTC)).total_seconds())),
        expires=session.expires_at,
    )
    return response


def register_auth(app: FastAPI, service: IdentityService) -> None:
    app.state.identity = service
    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    router = APIRouter(prefix="/api/v1")

    @app.exception_handler(AuthError)
    async def auth_error(request: Request, error: AuthError) -> JSONResponse:
        return error_response(error)

    @app.exception_handler(psycopg.Error)
    async def database_error(request: Request, error: psycopg.Error) -> JSONResponse:
        return error_response(
            AuthError(503, "SERVICE_UNAVAILABLE", "Service indisponible. Réessayer.")
        )

    @app.exception_handler(RateLimitExceeded)
    async def rate_error(request: Request, error: RateLimitExceeded) -> JSONResponse:
        return error_response(
            AuthError(429, "RATE_LIMITED", "Trop de requêtes, patientez une minute.")
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        # Ne jamais renvoyer l'entrée brute de Pydantic (peut contenir un mot de passe).
        issue = error.errors()[0]
        message = (
            "Champ obligatoire."
            if issue["type"] == "missing"
            else (
                "Adresse e-mail invalide."
                if issue["loc"][-1] == "email"
                else "Données de connexion invalides."
            )
        )
        return error_response(AuthError(400, "BAD_REQUEST", message))

    def origin(request: Request) -> None:
        allowed = os.environ.get("AUTH_ORIGIN", "https://localhost").rstrip("/")
        received = request.headers.get("origin")
        if (received and received.rstrip("/") != allowed) or request.headers.get(
            "sec-fetch-site"
        ) == "cross-site":
            raise AuthError(403, "FORBIDDEN", "Action non autorisée.")

    @router.post("/auth/login", response_model=SessionResponse)
    @limiter.limit("10/minute")
    def login(request: Request, payload: LoginInput) -> JSONResponse:
        origin(request)
        ip = request.client.host if request.client else "0.0.0.0"
        return session_response(
            service.login(
                payload.email,
                payload.password,
                ip,
                request.headers.get("user-agent", ""),
            )
        )

    @router.post("/auth/refresh", response_model=SessionResponse)
    def refresh(request: Request) -> JSONResponse:
        origin(request)
        return session_response(
            service.refresh(
                request.cookies.get(COOKIE, ""), request.headers.get("user-agent", "")
            )
        )

    @router.post("/auth/logout", status_code=204)
    def logout(request: Request) -> Response:
        origin(request)
        service.logout(request.cookies.get(COOKIE, ""))
        response = Response(status_code=204, headers={"Cache-Control": "no-store"})
        response.delete_cookie(
            COOKIE, path=COOKIE_PATH, httponly=True, secure=True, samesite="strict"
        )
        return response

    @router.get("/me", response_model=UserResponse)
    def me(user: Annotated[User, Depends(current_user)]) -> JSONResponse:
        return JSONResponse(asdict(user), headers={"Cache-Control": "no-store"})

    app.include_router(router)
