from datetime import datetime

from rest_framework.permissions import BasePermission
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import TokenError

__all__ = [
    "JWTAuthentication",
    "get_request_role",
    "get_client_id",
    "IsTrainerRole",
    "IsClientRole",
    "IsAdminRole",
    "IsTrainerOrBillingRole",
    "issue_client_jwt",
    "issue_trainer_jwt",
    "issue_admin_jwt",
    "issue_billing_jwt",
    "parse_token_claims",
]


def get_request_role(request) -> str:
    token = getattr(request, "auth", None)
    if token is None:
        return ""
    return str(token.payload.get("role", ""))


def get_client_id(request) -> int | None:
    token = getattr(request, "auth", None)
    if token is None:
        return None
    cid = token.payload.get("client_id")
    return int(cid) if cid is not None else None


class RolePermission(BasePermission):
    required_role = ""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated) and (
            get_request_role(request) == self.required_role
        )


class IsTrainerRole(RolePermission):
    required_role = "trainer"


class IsClientRole(RolePermission):
    required_role = "client"


class IsAdminRole(RolePermission):
    required_role = "admin"


class IsTrainerOrBillingRole(RolePermission):
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return get_request_role(request) in ("trainer", "billing")


def issue_client_jwt(client) -> dict:
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken()
    refresh["role"] = "client"
    refresh["client_id"] = client.id
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


def issue_trainer_jwt(trainer) -> dict:
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken()
    refresh["role"] = "trainer"
    refresh["trainer_id"] = trainer.id
    refresh["user_id"] = trainer.id
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


def issue_admin_jwt(trainer) -> dict:
    from rest_framework_simplejwt.tokens import RefreshToken

    refresh = RefreshToken()
    refresh["role"] = "admin"
    refresh["user_id"] = trainer.id
    refresh["trainer_id"] = trainer.id
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


def issue_billing_jwt(trainer) -> str:
    from rest_framework_simplejwt.tokens import AccessToken

    token = AccessToken()
    token["role"] = "billing"
    token["user_id"] = trainer.id
    token["trainer_id"] = trainer.id
    return str(token)


def parse_token_claims(token_str: str) -> dict | None:
    from rest_framework_simplejwt.tokens import AccessToken

    try:
        token = AccessToken(token_str)
        return dict(token.payload)
    except Exception:
        return None


def token_expiry_iso(token_str: str) -> str | None:
    claims = parse_token_claims(token_str)
    if not claims:
        return None
    exp = claims.get("exp")
    if not exp:
        return None
    return datetime.fromtimestamp(exp).isoformat()
