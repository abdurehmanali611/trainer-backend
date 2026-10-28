"""Client-facing auth endpoints — called by the trainer-client gateway."""
from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Trainer
from apps.core.auth import issue_client_jwt, parse_token_claims
from apps.core.utils import make_reset_token, read_reset_token, send_reset_email
from apps.fitness.models import Client, Payment
from apps.fitness.services import (
    client_access_state,
    client_payment_payload,
    notify_trainer,
    payment_instruction_payload,
)


class ServiceTokenPermission:
    def __call__(self, request):
        return request.headers.get("X-Service-Token", "") == settings.SERVICE_TOKEN


def require_client(request) -> Client:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise PermissionDenied("Missing client token.")
    claims = parse_token_claims(auth[7:])
    if not claims or claims.get("role") != "client":
        raise PermissionDenied("Invalid client token.")
    client = Client.objects.filter(pk=claims.get("client_id"), is_active=True).first()
    if not client:
        raise PermissionDenied("Client not found.")
    return client


class ClientLoginView(APIView):
    """POST {phone, credential} — credential is OTP (first login) or the
    password they set. Returns JWT unless blocked by subscription gate."""

    authentication_classes = []
    permission_classes = [ServiceTokenPermission]

    def post(self, request):
        phone = (request.data.get("phone") or "").strip()
        credential = (request.data.get("credential") or "").strip()
        if not phone or not credential:
            return Response(
                {"detail": "phone and credential are required."}, status=400
            )
        client = Client.objects.filter(phone=phone, is_active=True).first()
        if not client or client.effective_credential != credential:
            return Response(
                {"detail": "Invalid phone or credential."}, status=401
            )
        access = client_access_state(client)
        billing = client_payment_payload(client)
        if access["state"] != "allowed":
            return Response(
                {
                    "blocked": True,
                    "reason": access["state"],
                    "billing": billing,
                },
                status=403,
            )
        tokens = issue_client_jwt(client)
        return Response(
            {
                "blocked": False,
                "must_change_credential": client.must_change_credential,
                "client": {
                    "id": client.id,
                    "name": client.name,
                    "phone": client.phone,
                    "email": client.email,
                    "mode": client.mode,
                    "avatar_url": client.avatar_url,
                },
                **tokens,
            }
        )


class ClientAccessStatusView(APIView):
    """Lock screen: {phone} -> blocked + billing payload (no JWT needed)."""

    authentication_classes = []
    permission_classes = [ServiceTokenPermission]

    def post(self, request):
        phone = (request.data.get("phone") or "").strip()
        client = Client.objects.filter(phone=phone, is_active=True).first()
        if not client:
            return Response({"found": False})
        access = client_access_state(client)
        billing = client_payment_payload(client)
        if access["state"] == "allowed":
            return Response({"found": True, "blocked": False, "billing": billing})
        return Response({"found": True, "blocked": True, "billing": billing})


class ClientLockPaymentSubmitView(APIView):
    """Blocked client submits a transaction id without logging in."""

    authentication_classes = []
    permission_classes = [ServiceTokenPermission]

    def post(self, request):
        phone = (request.data.get("phone") or "").strip()
        client = Client.objects.filter(phone=phone, is_active=True).first()
        if not client:
            return Response({"detail": "No account for this phone."}, status=404)
        transaction_id = (request.data.get("transaction_id") or "").strip()
        channel = request.data.get("channel", "telebirr")
        if not transaction_id:
            return Response({"detail": "transaction_id is required."}, status=400)
        billing = client_payment_payload(client)
        invoice_id = (billing.get("invoice") or {}).get("id")
        if not invoice_id:
            return Response(
                {"detail": "No pending invoice. Please contact your trainer."},
                status=400,
            )
        payment = Payment.objects.create(
            invoice_id=invoice_id,
            client=client,
            transaction_id=transaction_id,
            channel=channel if channel in ("cash", "bank", "telebirr") else "telebirr",
        )
        notify_trainer(
            client.trainer,
            "Payment submitted",
            f"{client.name} submitted {payment.transaction_id} ({payment.channel}) — awaiting approval.",
            "payment",
            {"payment_id": payment.id, "client_id": client.id},
        )
        return Response(
            {"detail": "Payment submitted. Your trainer will review it.", "payment_id": payment.id}
        )


class ClientChangeCredentialView(APIView):
    """First login: client replaces the OTP with their own credential."""

    authentication_classes = []
    permission_classes = [ServiceTokenPermission]

    def post(self, request):
        client = require_client(request)
        new_cred = (request.data.get("new_credential") or "").strip()
        if len(new_cred) < 4:
            return Response(
                {"detail": "Credential must be at least 4 characters."}, status=400
            )
        client.credential = new_cred
        client.must_change_credential = False
        client.save(update_fields=["credential", "must_change_credential"])
        return Response({"detail": "Credential updated."})


class ClientResetRequestView(APIView):
    authentication_classes = []
    permission_classes = [ServiceTokenPermission]

    def post(self, request):
        email = (request.data.get("email") or "").strip()
        client = Client.objects.filter(email__iexact=email, is_active=True).first()
        if client:
            token = make_reset_token(client.id, "client")
            reset_url = f"{settings.CLIENT_APP_RESET_URL}?token={token}"
            send_reset_email(client.email, client.name, reset_url)
        return Response({"detail": "If that email exists, a reset link was sent."})


class ClientResetConfirmView(APIView):
    authentication_classes = []
    permission_classes = [ServiceTokenPermission]

    def post(self, request):
        parsed = read_reset_token(request.data.get("token", ""))
        if not parsed or parsed[0] != "client":
            return Response({"detail": "Invalid or expired reset link."}, status=400)
        client = Client.objects.filter(id=parsed[1], is_active=True).first()
        if not client:
            return Response({"detail": "Invalid or expired reset link."}, status=400)
        new_cred = (request.data.get("new_credential") or "").strip()
        if len(new_cred) < 4:
            return Response(
                {"detail": "Credential must be at least 4 characters."}, status=400
            )
        client.credential = new_cred
        client.must_change_credential = False
        client.save(update_fields=["credential", "must_change_credential"])
        return Response({"detail": "Credential updated. You can now log in."})
