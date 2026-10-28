from __future__ import annotations

from django.contrib.auth import authenticate
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.auth import IsTrainerRole

from .models import AdminChatMessage, PlatformPayment
from .services import (
    billing_payload,
    chat_thread_payload,
    create_setup_payment,
    display_name,
    ensure_billing,
    pending_payment,
    submit_quarterly_payment,
)


class PlatformBillingView(APIView):
    permission_classes = [IsTrainerRole]

    def get(self, request):
        billing = ensure_billing(request.user)
        payments = PlatformPayment.objects.filter(trainer=request.user)[:20]
        return Response(
            {
                "billing": billing_payload(billing),
                "payments": [
                    {
                        "id": p.id,
                        "kind": p.kind,
                        "status": p.status,
                        "amount_etb": float(p.amount_etb),
                        "channel": p.channel,
                        "transaction_ref": p.transaction_ref,
                        "submitted_at": p.submitted_at,
                        "review_note": p.review_note,
                    }
                    for p in payments
                ],
            }
        )


class LockedBillingView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def post(self, request):
        username = str(request.data.get("username", "")).strip()
        password = str(request.data.get("password", ""))
        if not username or not password:
            return Response({"detail": "Username and password are required."}, status=400)
        trainer = authenticate(request, username=username, password=password)
        if not trainer or trainer.is_superuser:
            return Response({"detail": "Invalid credentials."}, status=401)
        billing = ensure_billing(trainer)
        return Response(
            {
                "billing": billing_payload(billing),
                "display_name": display_name(trainer),
            }
        )


class PlatformPaymentSubmitView(APIView):
    permission_classes = [IsTrainerRole]

    def post(self, request):
        billing = ensure_billing(request.user)
        channel = str(request.data.get("channel", "")).strip()
        transaction_ref = str(request.data.get("transaction_ref", "")).strip()
        if not channel or not transaction_ref:
            return Response(
                {"detail": "Payment channel and transaction number are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if pending_payment(billing, "setup" if not billing.setup_fee_paid else "quarterly"):
            return Response(
                {"detail": "A payment reference is already waiting for review."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            if not billing.setup_fee_paid:
                payment = create_setup_payment(request.user, channel, transaction_ref)
            else:
                payment = submit_quarterly_payment(request.user, channel, transaction_ref)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "detail": "Payment reference submitted. Apex will review it.",
                "payment_id": payment.id,
                "billing": billing_payload(billing),
            },
            status=status.HTTP_201_CREATED,
        )


class LockedPaymentSubmitView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def post(self, request):
        username = str(request.data.get("username", "")).strip()
        password = str(request.data.get("password", ""))
        channel = str(request.data.get("channel", "")).strip()
        transaction_ref = str(request.data.get("transaction_ref", "")).strip()
        if not username or not password:
            return Response({"detail": "Username and password are required."}, status=400)
        if not channel or not transaction_ref:
            return Response(
                {"detail": "Payment channel and transaction number are required."}, status=400
            )
        trainer = authenticate(request, username=username, password=password)
        if not trainer or trainer.is_superuser:
            return Response({"detail": "Invalid credentials."}, status=401)
        billing = ensure_billing(trainer)
        if pending_payment(billing, "setup" if not billing.setup_fee_paid else "quarterly"):
            return Response(
                {"detail": "A payment reference is already waiting for review."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            if not billing.setup_fee_paid:
                payment = create_setup_payment(trainer, channel, transaction_ref)
            else:
                payment = submit_quarterly_payment(trainer, channel, transaction_ref)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(
            {
                "detail": "Payment reference submitted. Apex will review it.",
                "payment_id": payment.id,
                "billing": billing_payload(billing),
            },
            status=201,
        )


class PlatformChatView(APIView):
    permission_classes = [IsTrainerRole]

    def get(self, request):
        trainer = request.user
        messages = AdminChatMessage.objects.filter(trainer=trainer).order_by("created_at")
        messages.filter(sender="admin", trainer_read_at__isnull=True).update(
            trainer_read_at=timezone.now()
        )
        return Response(
            {
                "thread": chat_thread_payload(trainer),
                "messages": [
                    {
                        "id": m.id,
                        "sender": m.sender,
                        "body": m.body,
                        "image_url": m.image_url,
                        "media_urls": m.media_urls,
                        "is_broadcast": m.is_broadcast,
                        "created_at": m.created_at,
                    }
                    for m in messages
                ],
            }
        )

    def post(self, request):
        body = str(request.data.get("body", "")).strip()
        image_url = str(request.data.get("image_url", "")).strip()
        media_urls = request.data.get("media_urls") or []
        if not body and not image_url and not media_urls:
            return Response({"detail": "Message is empty."}, status=400)
        message = AdminChatMessage.objects.create(
            trainer=request.user,
            sender="trainer",
            body=body,
            image_url=image_url,
            media_urls=media_urls if isinstance(media_urls, list) else [],
            trainer_read_at=timezone.now(),
        )
        return Response({"id": message.id, "created_at": message.created_at}, status=201)


class PlatformChatUnreadView(APIView):
    permission_classes = [IsTrainerRole]

    def get(self, request):
        unread = AdminChatMessage.objects.filter(
            trainer=request.user, sender="admin", trainer_read_at__isnull=True
        ).count()
        return Response({"unread": unread, "name": display_name(request.user)})
