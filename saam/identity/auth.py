"""Sessions et verrouillage, avec état PostgreSQL partagé entre les processus."""

from __future__ import annotations

import hashlib
import ipaddress
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import jwt
import psycopg
from psycopg.rows import dict_row

from saam.identity.passwords import hash_password, verify_password
from saam.identity.seed import Role

DUMMY_HASH = hash_password("nonexistent-account-placeholder")
ISSUER = "saamstiahf-api"
AUDIENCE = "saamstiahf-ui"


@dataclass
class AuthError(Exception):
    status: int
    code: str
    message: str


@dataclass(frozen=True)
class User:
    id: str
    email: str
    display_name: str
    role: Role

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> User:
        return cls(
            str(row["id"]), row["email"], row["display_name"], cast(Role, row["role"])
        )


@dataclass(frozen=True)
class Session:
    access_token: str
    refresh_token: str
    expires_at: datetime
    user: User


def token_hash(token: str) -> str:
    # SHA-256 d'un secret opaque de session, jamais d'un artefact/manifeste JSON.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IdentityService:
    database_url: str
    jwt_secret: str

    @classmethod
    def from_environment(cls) -> IdentityService:
        return cls(
            os.environ.get("DATABASE_URL_API", ""), os.environ.get("JWT_SECRET", "")
        )

    def ready(self) -> None:
        if not self.database_url or len(self.jwt_secret.encode("utf-8")) < 32:
            raise AuthError(
                503, "SERVICE_UNAVAILABLE", "Service indisponible. Réessayer."
            )

    def connect(self) -> psycopg.Connection[dict[str, Any]]:
        self.ready()
        return psycopg.connect(
            self.database_url,
            row_factory=dict_row,
            connect_timeout=3,
            options="-c statement_timeout=5000",
        )

    def session(
        self,
        connection: psycopg.Connection[dict[str, Any]],
        row: dict[str, Any],
        expires: datetime,
        agent: str,
    ) -> Session:
        user = User.from_row(row)
        now = datetime.now(UTC)
        access = jwt.encode(
            {
                "sub": user.id,
                "iat": now,
                "exp": now + timedelta(minutes=30),
                "jti": secrets.token_hex(16),
                "type": "access",
                "iss": ISSUER,
                "aud": AUDIENCE,
            },
            self.jwt_secret,
            algorithm="HS256",
        )
        refresh = secrets.token_urlsafe(48)
        connection.execute(
            "INSERT INTO refresh_tokens (user_id, token_hash, expires_at, user_agent) VALUES (%s, %s, %s, %s)",
            (UUID(user.id), token_hash(refresh), expires, agent[:300]),
        )
        return Session(access, refresh, expires, user)

    def login(self, email: str, password: str, ip: str, agent: str = "") -> Session:
        email = email.strip().lower()
        ip = str(ipaddress.ip_address(ip))
        with self.connect() as connection:
            try:
                # Toujours IP puis compte : ordre unique, limite commune à tous les workers.
                connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    ("login-ip:" + ip,),
                )
                connection.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    ("login-email:" + email,),
                )
                now_row = connection.execute("SELECT now() AS current_time").fetchone()
                assert now_row is not None
                now = now_row["current_time"]
                attempts = connection.execute(
                    "SELECT count(*) AS count FROM login_attempts WHERE ip=%s::inet AND attempted_at >= now()-interval '1 minute'",
                    (ip,),
                ).fetchone()
                assert attempts is not None
                if attempts["count"] >= 10:
                    raise AuthError(
                        429, "RATE_LIMITED", "Trop de requêtes, patientez une minute."
                    )
                row = connection.execute(
                    "SELECT * FROM users WHERE email=%s FOR UPDATE", (email,)
                ).fetchone()
                if row and row["locked_until"] and row["locked_until"] > now:
                    connection.execute(
                        "INSERT INTO login_attempts (email, ip, succeeded) VALUES (%s, %s::inet, false)",
                        (email, ip),
                    )
                    raise AuthError(
                        423,
                        "ACCOUNT_LOCKED",
                        "Trop de tentatives. Réessayez dans 15 minutes.",
                    )
                valid = verify_password(
                    row["password_hash"] if row else DUMMY_HASH, password
                )
                successful = bool(row and valid and row["is_active"])
                connection.execute(
                    "INSERT INTO login_attempts (email, ip, succeeded) VALUES (%s, %s::inet, %s)",
                    (email, ip, successful),
                )
                if not row or not valid:
                    if row:
                        failures = connection.execute(
                            "SELECT count(*) AS count FROM login_attempts WHERE email=%s AND NOT succeeded AND attempted_at >= now()-interval '15 minutes'",
                            (email,),
                        ).fetchone()
                        assert failures is not None
                        if failures["count"] >= 5:
                            connection.execute(
                                "UPDATE users SET locked_until=now()+interval '15 minutes' WHERE id=%s",
                                (row["id"],),
                            )
                    raise AuthError(
                        401, "INVALID_CREDENTIALS", "E-mail ou mot de passe incorrect."
                    )
                if not row["is_active"]:
                    raise AuthError(
                        403,
                        "ACCOUNT_DISABLED",
                        "Compte désactivé. Contactez un administrateur.",
                    )
                connection.execute(
                    "UPDATE users SET last_login_at=now(), locked_until=NULL WHERE id=%s",
                    (row["id"],),
                )
                return self.session(connection, row, now + timedelta(hours=8), agent)
            except AuthError:
                # Les tentatives et le verrouillage doivent survivre au refus HTTP.
                connection.commit()
                raise

    def refresh(self, token: str, agent: str = "") -> Session:
        if not token or len(token) > 256:
            raise AuthError(
                401, "UNAUTHENTICATED", "Session expirée. Reconnectez-vous."
            )
        with self.connect() as connection:
            row = connection.execute(
                "SELECT u.*, t.id AS refresh_id, t.expires_at FROM refresh_tokens t JOIN users u ON u.id=t.user_id "
                "WHERE t.token_hash=%s AND t.revoked_at IS NULL AND t.expires_at > now() FOR UPDATE OF t, u",
                (token_hash(token),),
            ).fetchone()
            if not row:
                raise AuthError(
                    401, "UNAUTHENTICATED", "Session expirée. Reconnectez-vous."
                )
            if not row["is_active"]:
                raise AuthError(
                    403,
                    "ACCOUNT_DISABLED",
                    "Compte désactivé. Contactez un administrateur.",
                )
            connection.execute(
                "UPDATE refresh_tokens SET revoked_at=now() WHERE id=%s",
                (row["refresh_id"],),
            )
            # Rotation à usage unique, sans prolonger la session initiale de huit heures.
            return self.session(connection, row, row["expires_at"], agent)

    def logout(self, token: str) -> None:
        if not token or len(token) > 256:
            raise AuthError(
                401, "UNAUTHENTICATED", "Session expirée. Reconnectez-vous."
            )
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id FROM refresh_tokens WHERE token_hash=%s AND revoked_at IS NULL AND expires_at > now() FOR UPDATE",
                (token_hash(token),),
            ).fetchone()
            if not row:
                raise AuthError(
                    401, "UNAUTHENTICATED", "Session expirée. Reconnectez-vous."
                )
            connection.execute(
                "UPDATE refresh_tokens SET revoked_at=now() WHERE id=%s", (row["id"],)
            )

    def profile(self, token: str) -> User:
        self.ready()
        try:
            claims = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=["HS256"],
                issuer=ISSUER,
                audience=AUDIENCE,
                options={"require": ["sub", "exp", "iat", "jti", "type"]},
            )
            if claims["type"] != "access":
                raise ValueError("Type de jeton incorrect")
            user_id = UUID(claims["sub"])
        except (jwt.InvalidTokenError, ValueError, TypeError) as error:
            raise AuthError(
                401, "UNAUTHENTICATED", "Session expirée. Reconnectez-vous."
            ) from error
        with self.connect() as connection:
            row = connection.execute(
                "SELECT id, email, display_name, role, is_active FROM users WHERE id=%s",
                (user_id,),
            ).fetchone()
        if not row:
            raise AuthError(
                401, "UNAUTHENTICATED", "Session expirée. Reconnectez-vous."
            )
        if not row["is_active"]:
            raise AuthError(
                403,
                "ACCOUNT_DISABLED",
                "Compte désactivé. Contactez un administrateur.",
            )
        return User.from_row(row)
