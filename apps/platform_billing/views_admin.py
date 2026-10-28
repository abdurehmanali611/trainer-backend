from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import authenticate
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Trainer
from apps.core.auth import issue_admin_jwt, parse_token_claims
from apps.fitness.models import Client, Session

from .models import (
    AdminAuditLog,
    AdminChatMessage,
    PlatformPayment,
    PricingPlan,
    SalesAgent,
    TrainerBilling,
)
from .services import (
    approve_payment,
    billing_payload,
    billing_state,
    broadcast_to_trainers,
    chat_thread_payload,
    display_name,
    ensure_billing,
    log_action,
    plan_fees,
    reject_payment,
    set_trial_end,
    today,
)


def _service_ok(request) -> bool:
    return request.headers.get("X-Service-Token", "") == settings.SERVICE_TOKEN


def _admin_from_request(request):
    auth = request.headers.get("Authorization", "") or request.META.get("HTTP_AUTHORIZATION", "")
    if not auth.startswith("Bearer "):
        raise PermissionDenied("Missing admin token.")
    claims = parse_token_claims(auth[7:])
    if not claims or claims.get("role") != "admin":
        raise PermissionDenied("Invalid admin token.")
    admin = Trainer.objects.filter(pk=claims.get("user_id"), is_superuser=True).first()
    if not admin:
        raise PermissionDenied("Admin not found.")
    return admin


class AdminBaseView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def initial(self, request, *args, **kwargs):
        if not _service_ok(request):
            raise PermissionDenied("Invalid service token.")
        self.admin = _admin_from_request(request)
        super().initial(request, *args, **kwargs)


def _num(value) -> float:
    return float(value or 0)


def trainer_row(trainer: Trainer) -> dict:
    billing = ensure_billing(trainer)
    state = billing_state(billing)
    unread = AdminChatMessage.objects.filter(
        trainer=trainer, sender="trainer", admin_read_at__isnull=True
    ).count()
    return {
        "tinNumber": str(trainer.id),
        "hotelDisplayName": display_name(trainer),
        "businessType": "gym",
        "accountStatus": billing.account_status,
        "subscriptionStatus": state,
        "setupFeeApproved": billing.setup_fee_paid,
        "setupFeeETB": _num(billing.setup_fee_etb),
        "quarterlyFeeETB": _num(billing.quarterly_fee_etb),
        "ownerUserName": trainer.username,
        "createdAt": trainer.created_at,
        "billingHold": billing.billing_hold,
        "isIllustrationTenant": billing.is_illustration,
        "unreadFeedback": unread,
        "salesAgentId": billing.sales_agent_id,
        "salesAgentName": billing.sales_agent.name if billing.sales_agent_id else None,
        "freeTrialEndsAt": billing.free_trial_ends_at,
        "paidUntil": billing.paid_until,
    }


def payment_row(payment: PlatformPayment) -> dict:
    trainer = payment.trainer
    billing = ensure_billing(trainer)
    return {
        "id": payment.id,
        "tinNumber": str(trainer.id),
        "hotelDisplayName": display_name(trainer),
        "paymentKind": payment.kind,
        "amountETB": _num(payment.amount_etb),
        "paymentChannel": payment.channel,
        "transactionRef": payment.transaction_ref,
        "status": payment.status,
        "submittedAt": payment.submitted_at,
        "cafeOrderMode": None,
        "salesAgentId": billing.sales_agent_id,
        "salesAgentName": billing.sales_agent.name if billing.sales_agent_id else None,
    }


def recent_payment(payment: PlatformPayment) -> dict:
    return {
        "id": payment.id,
        "paymentKind": payment.kind,
        "amountETB": _num(payment.amount_etb),
        "status": payment.status,
        "transactionRef": payment.transaction_ref,
        "submittedAt": payment.submitted_at,
    }


def trainer_detail(trainer: Trainer) -> dict:
    billing = ensure_billing(trainer)
    plan = plan_fees()
    row = trainer_row(trainer)
    clients = Client.objects.filter(trainer=trainer)
    user = {
        "id": trainer.id,
        "UserName": trainer.username,
        "Role": "Trainer",
        "loginDisabled": not trainer.is_active,
        "loginDisabledReason": billing.status_reason or None,
        "createdAt": trainer.created_at,
    }
    return {
        **row,
        "modules": [],
        "logoUrl": None,
        "suggestedSetupFeeETB": _num(plan[0]),
        "suggestedQuarterlyFeeETB": _num(plan[1]),
        "feesManuallySet": _num(billing.setup_fee_etb) != _num(plan[0])
        or _num(billing.quarterly_fee_etb) != _num(plan[1]),
        "pricingRuleId": None,
        "feesMatchCatalog": _num(billing.setup_fee_etb) == _num(plan[0])
        and _num(billing.quarterly_fee_etb) == _num(plan[1]),
        "subscriptionPaymentApproved": billing.setup_fee_paid,
        "subscriptionPaidUntil": billing.paid_until,
        "paidQuartersCount": billing.paid_quarters_count,
        "billingStartedAt": billing.billing_started_at,
        "freeTrialEndsAt": billing.free_trial_ends_at,
        "billingNotes": billing.billing_notes or None,
        "paymentChannel": billing.setup_channel or None,
        "paymentTransactionRef": billing.setup_transaction_ref or None,
        "ownerUserName": trainer.username,
        "suspendedReason": billing.status_reason if billing.account_status == "suspended" else None,
        "bannedReason": billing.status_reason if billing.account_status == "banned" else None,
        "users": [user],
        "recentPayments": [
            recent_payment(p)
            for p in PlatformPayment.objects.filter(trainer=trainer)[:50]
        ],
        "operationalSnapshot": {
            "staffCount": 1,
            "ordersToday": 0,
            "openOrders": 0,
            "pendingPurchaseRequests": 0,
            "pendingStockOutRequests": 0,
            "pendingItemRegistrations": 0,
            "clientCount": clients.count(),
            "sessionCount": Session.objects.filter(trainer=trainer).count(),
        },
        "cafeOrderMode": "",
        "cafeOrderModeHistory": [],
        "waiterOrderingEnabled": False,
        "hrSoloManagerEnabled": False,
        "hrBiometricsEnabled": False,
        "clientCount": clients.count(),
        "email": trainer.email,
        "phone": trainer.phone,
        "fullName": trainer.full_name,
        "gymName": trainer.gym_name,
        "isLoginActive": trainer.is_active,
        "billing": billing_payload(billing),
    }


class AdminLoginView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def post(self, request):
        if not _service_ok(request):
            raise PermissionDenied("Invalid service token.")
        username = str(request.data.get("username", "")).strip()
        password = str(request.data.get("password", ""))
        user = authenticate(request, username=username, password=password)
        if not user or not user.is_superuser or not user.is_active:
            return Response(
                {"detail": "Invalid admin credentials."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        tokens = issue_admin_jwt(user)
        return Response(
            {
                **tokens,
                "member": {
                    "id": user.id,
                    "UserName": user.username,
                    "displayName": user.full_name or user.username,
                    "role": "Admin",
                },
            }
        )


class DashboardSummaryView(AdminBaseView):
    def get(self, request):
        trainers = list(Trainer.objects.filter(is_superuser=False))
        states = {}
        setup_pending = 0
        trials_ending = 0
        trial_expired = 0
        suspended = 0
        banned = 0
        holds = 0
        inactive = 0
        for trainer in trainers:
            billing = ensure_billing(trainer)
            state = billing_state(billing)
            states[state] = states.get(state, 0) + 1
            if not billing.setup_fee_paid:
                setup_pending += 1
            if state == "trial_ending":
                trials_ending += 1
            if state == "expired":
                trial_expired += 1
            if state == "suspended":
                suspended += 1
            if state == "banned":
                banned += 1
            if billing.billing_hold:
                holds += 1
            if state in ("expired", "setup_pending", "setup_required", "on_hold"):
                inactive += 1
        pending_setup = PlatformPayment.objects.filter(kind="setup", status="pending").count()
        pending_quarterly = PlatformPayment.objects.filter(
            kind="quarterly", status="pending"
        ).count()
        unread = AdminChatMessage.objects.filter(
            sender="trainer", admin_read_at__isnull=True
        ).count()
        clients = Client.objects.all()
        active_trainers = states.get("active", 0) + states.get("warning", 0)
        plan = plan_fees()
        return Response(
            {
                "pendingSetupPayments": pending_setup,
                "pendingQuarterlyPayments": pending_quarterly,
                "pendingYearlyPayments": 0,
                "unreadFeedback": unread,
                "suspendedTenants": suspended,
                "bannedTenants": banned,
                "setupPendingTenants": setup_pending,
                "inactiveTenants": inactive,
                "billingHoldTenants": holds,
                "graceOrExpiredTenants": states.get("expired", 0),
                "trialsEndingSoon": trials_ending,
                "trialExpiredTenants": trial_expired,
                "totalTenants": len(trainers),
                "totalUsers": clients.count(),
                "disabledUsers": clients.filter(is_active=False).count(),
                "pendingModuleRequests": 0,
                "pendingOrderModeRequests": 0,
                "tenantsByBusinessType": [
                    {"businessType": "gym", "label": "Trainers", "count": len(trainers)}
                ],
                "activeTrainers": active_trainers,
                "trialTrainers": states.get("trial", 0) + trials_ending,
                "expiredTrainers": states.get("expired", 0),
                "setupPendingTrainers": setup_pending,
                "totalClients": clients.count(),
                "quarterlyRecurringETB": _num(plan[1]) * active_trainers,
                "setupPipelineETB": _num(plan[0]) * setup_pending,
            }
        )


class TrainersView(AdminBaseView):
    def get(self, request):
        qs = Trainer.objects.filter(is_superuser=False).order_by("-created_at")
        search = str(request.query_params.get("search", "")).strip()
        if search:
            qs = qs.filter(
                Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(full_name__icontains=search)
                | Q(gym_name__icontains=search)
                | Q(phone__icontains=search)
            )
        status_filter = str(request.query_params.get("status", "")).strip()
        rows = [trainer_row(t) for t in qs]
        if status_filter:
            rows = [r for r in rows if r["subscriptionStatus"] == status_filter]
        return Response(rows)

    def post(self, request):
        data = request.data
        username = str(data.get("username", "")).strip()
        password = str(data.get("password", ""))
        email = str(data.get("email", "")).strip()
        if not username or not password:
            return Response({"detail": "Username and password are required."}, status=400)
        if Trainer.objects.filter(username__iexact=username).exists():
            return Response({"detail": "That username is already taken."}, status=400)
        if not email:
            email = f"{username}@trainer.local"
        if Trainer.objects.filter(email__iexact=email).exists():
            return Response({"detail": "That email is already in use."}, status=400)
        trainer = Trainer.objects.create_user(
            username=username,
            password=password,
            email=email,
            full_name=str(data.get("full_name", "")).strip(),
            gym_name=str(data.get("gym_name", "")).strip(),
            phone=str(data.get("phone", "")).strip(),
        )
        billing = ensure_billing(trainer)
        setup_fee, quarterly_fee = plan_fees()
        billing.setup_fee_etb = setup_fee
        billing.quarterly_fee_etb = quarterly_fee
        billing.setup_fee_paid = True
        billing.setup_approved_at = timezone.now()
        billing.billing_started_at = today()
        billing.paid_until = today() + timedelta(days=90)
        agent_id = data.get("sales_agent_id")
        if agent_id:
            billing.sales_agent_id = int(agent_id)
        billing.save()
        PlatformPayment.objects.create(
            trainer=trainer,
            kind="setup",
            amount_etb=setup_fee,
            channel="admin",
            transaction_ref="setup handled by admin",
            status="approved",
            source="admin",
            reviewed_by=self.admin,
            reviewed_at=timezone.now(),
        )
        log_action(self.admin, "trainer.create", trainer, label=display_name(trainer))
        return Response(trainer_detail(trainer), status=201)


class TrainerDetailView(AdminBaseView):
    def get(self, request, trainer_id: int):
        trainer = Trainer.objects.filter(pk=trainer_id, is_superuser=False).first()
        if not trainer:
            return Response({"detail": "Trainer not found."}, status=404)
        return Response(trainer_detail(trainer))


class TrainerBillingView(AdminBaseView):
    def patch(self, request, trainer_id: int):
        trainer = Trainer.objects.filter(pk=trainer_id, is_superuser=False).first()
        if not trainer:
            return Response({"detail": "Trainer not found."}, status=404)
        billing = ensure_billing(trainer)
        data = request.data
        if "setupFeeETB" in data:
            billing.setup_fee_etb = Decimal(str(data["setupFeeETB"] or 0))
        if "quarterlyFeeETB" in data:
            billing.quarterly_fee_etb = Decimal(str(data["quarterlyFeeETB"] or 0))
        if "billingNotes" in data:
            billing.billing_notes = str(data.get("billingNotes") or "")
        if "isIllustrationTenant" in data:
            billing.is_illustration = bool(data["isIllustrationTenant"])
        if "billingHold" in data:
            billing.billing_hold = bool(data["billingHold"])
        if "salesAgentId" in data:
            billing.sales_agent_id = data["salesAgentId"] or None
        billing.save()
        if "freeTrialEndsAt" in data:
            raw = data["freeTrialEndsAt"]
            trial_end = None
            if raw:
                trial_end = date.fromisoformat(str(raw)[:10])
            set_trial_end(trainer, trial_end)
        log_action(self.admin, "trainer.billing", trainer, label=display_name(trainer))
        return Response(trainer_detail(trainer))


class TrainerAccessView(AdminBaseView):
    def post(self, request, trainer_id: int):
        trainer = Trainer.objects.filter(pk=trainer_id, is_superuser=False).first()
        if not trainer:
            return Response({"detail": "Trainer not found."}, status=404)
        billing = ensure_billing(trainer)
        action = str(request.data.get("action", "")).strip()
        reason = str(request.data.get("reason", "")).strip()
        if action == "suspend":
            billing.account_status = "suspended"
            billing.status_reason = reason
        elif action == "unsuspend":
            billing.account_status = "active"
            billing.status_reason = ""
        elif action == "ban":
            billing.account_status = "banned"
            billing.status_reason = reason
            trainer.is_active = False
        elif action == "unban":
            billing.account_status = "active"
            billing.status_reason = ""
            trainer.is_active = True
        elif action == "delete":
            billing.account_status = "deleted"
            billing.status_reason = reason
            trainer.is_active = False
        elif action == "restore":
            billing.account_status = "active"
            billing.status_reason = ""
            trainer.is_active = True
        elif action == "release_hold":
            billing.billing_hold = False
            if not billing.paid_until or billing.paid_until < today():
                billing.paid_until = today() + timedelta(days=90)
            if not billing.billing_started_at:
                billing.billing_started_at = today()
        else:
            return Response({"detail": "Unknown action."}, status=400)
        trainer.save(update_fields=["is_active"])
        billing.save()
        log_action(self.admin, f"trainer.{action}", trainer, reason, display_name(trainer))
        return Response(trainer_detail(trainer))


class TrainerPaymentsView(AdminBaseView):
    def get(self, request, trainer_id: int):
        payments = PlatformPayment.objects.filter(trainer_id=trainer_id)[:100]
        return Response([recent_payment(p) for p in payments])


class PendingPaymentsView(AdminBaseView):
    def get(self, request):
        kind = str(request.query_params.get("kind", "")).strip()
        qs = PlatformPayment.objects.filter(status="pending")
        if kind:
            qs = qs.filter(kind=kind)
        return Response([payment_row(p) for p in qs.order_by("submitted_at")])


class PaymentApproveView(AdminBaseView):
    def post(self, request, payment_id: int):
        payment = PlatformPayment.objects.filter(pk=payment_id, status="pending").first()
        if not payment:
            return Response({"detail": "Pending payment not found."}, status=404)
        approve_payment(payment, self.admin)
        log_action(
            self.admin,
            f"payment.approve.{payment.kind}",
            payment.trainer,
            label=display_name(payment.trainer),
        )
        return Response(payment_row(payment))


class PaymentRejectView(AdminBaseView):
    def post(self, request, payment_id: int):
        payment = PlatformPayment.objects.filter(pk=payment_id, status="pending").first()
        if not payment:
            return Response({"detail": "Pending payment not found."}, status=404)
        reason = str(request.data.get("reason", "")).strip()
        if not reason:
            return Response({"detail": "A rejection reason is required."}, status=400)
        reject_payment(payment, reason, self.admin)
        log_action(
            self.admin,
            f"payment.reject.{payment.kind}",
            payment.trainer,
            reason,
            display_name(payment.trainer),
        )
        return Response(payment_row(payment))


class PricingView(AdminBaseView):
    def get(self, request):
        plans = PricingPlan.objects.all()
        return Response(
            [
                {
                    "id": p.id,
                    "businessType": "gym",
                    "modulesKey": "trainer",
                    "modules": [],
                    "setupFeeETB": _num(p.setup_fee_etb),
                    "quarterlyFeeETB": _num(p.quarterly_fee_etb),
                    "description": p.description,
                    "isActive": p.is_active,
                    "createdAt": p.created_at,
                    "updatedAt": p.updated_at,
                }
                for p in plans
            ]
        )

    def post(self, request):
        data = request.data
        plan = PricingPlan.objects.create(
            setup_fee_etb=Decimal(str(data.get("setupFeeETB") or 15000)),
            quarterly_fee_etb=Decimal(str(data.get("quarterlyFeeETB") or 5000)),
            description=str(data.get("description") or ""),
            is_active=bool(data.get("isActive", True)),
        )
        log_action(self.admin, "pricing.create", label=str(plan.id))
        return Response({"id": plan.id}, status=201)


class PricingDetailView(AdminBaseView):
    def patch(self, request, plan_id: int):
        plan = PricingPlan.objects.filter(pk=plan_id).first()
        if not plan:
            return Response({"detail": "Pricing rule not found."}, status=404)
        data = request.data
        if "setupFeeETB" in data:
            plan.setup_fee_etb = Decimal(str(data["setupFeeETB"] or 0))
        if "quarterlyFeeETB" in data:
            plan.quarterly_fee_etb = Decimal(str(data["quarterlyFeeETB"] or 0))
        if "description" in data:
            plan.description = str(data.get("description") or "")
        if "isActive" in data:
            plan.is_active = bool(data["isActive"])
        plan.save()
        log_action(self.admin, "pricing.update", label=str(plan.id))
        return Response({"ok": True})

    def delete(self, request, plan_id: int):
        PricingPlan.objects.filter(pk=plan_id).delete()
        log_action(self.admin, "pricing.delete", label=str(plan_id))
        return Response({"ok": True})


class SalesAgentsView(AdminBaseView):
    def get(self, request):
        qs = SalesAgent.objects.all()
        if str(request.query_params.get("active", "")).lower() in ("1", "true"):
            qs = qs.filter(is_active=True)
        return Response(
            [
                {
                    "id": a.id,
                    "name": a.name,
                    "phone": a.phone,
                    "isActive": a.is_active,
                    "tenantCount": a.trainers.count(),
                    "createdAt": a.created_at,
                }
                for a in qs
            ]
        )

    def post(self, request):
        agent = SalesAgent.objects.create(
            name=str(request.data.get("name", "")).strip(),
            phone=str(request.data.get("phone", "")).strip(),
        )
        log_action(self.admin, "sales_agent.create", label=agent.name)
        return Response({"id": agent.id}, status=201)


class SalesAgentDetailView(AdminBaseView):
    def patch(self, request, agent_id: int):
        agent = SalesAgent.objects.filter(pk=agent_id).first()
        if not agent:
            return Response({"detail": "Sales agent not found."}, status=404)
        if "name" in request.data:
            agent.name = str(request.data.get("name") or "").strip()
        if "phone" in request.data:
            agent.phone = str(request.data.get("phone") or "").strip()
        if "isActive" in request.data:
            agent.is_active = bool(request.data["isActive"])
        agent.save()
        return Response({"ok": True})

    def delete(self, request, agent_id: int):
        SalesAgent.objects.filter(pk=agent_id).delete()
        return Response({"ok": True})


class ClientsView(AdminBaseView):
    def get(self, request):
        qs = Client.objects.select_related("trainer").order_by("-created_at")
        search = str(request.query_params.get("search", "")).strip()
        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(phone__icontains=search)
                | Q(email__icontains=search)
                | Q(trainer__username__icontains=search)
            )
        trainer_id = request.query_params.get("trainer")
        if trainer_id:
            qs = qs.filter(trainer_id=trainer_id)
        return Response(
            [
                {
                    "id": c.id,
                    "userName": c.name,
                    "role": "Client",
                    "tinNumber": str(c.trainer_id),
                    "hotelDisplayName": display_name(c.trainer),
                    "businessType": "gym",
                    "loginDisabled": not c.is_active,
                    "loginDisabledReason": None,
                    "createdAt": c.created_at,
                    "phone": c.phone,
                    "email": c.email,
                    "mode": c.mode,
                }
                for c in qs
            ]
        )


class ClientAccessView(AdminBaseView):
    def patch(self, request, client_id: int):
        client = Client.objects.filter(pk=client_id).first()
        if not client:
            return Response({"detail": "Client not found."}, status=404)
        if "disabled" in request.data:
            client.is_active = not bool(request.data["disabled"])
            client.save(update_fields=["is_active"])
            log_action(
                self.admin,
                "client.login_disabled" if not client.is_active else "client.login_enabled",
                client.trainer,
                label=client.name,
            )
        return Response({"ok": True})


class AuditView(AdminBaseView):
    def get(self, request):
        limit = min(int(request.query_params.get("limit", 100)), 500)
        rows = AdminAuditLog.objects.select_related("actor", "target_trainer")[:limit]
        return Response(
            [
                {
                    "id": r.id,
                    "action": r.action,
                    "targetTinNumber": str(r.target_trainer_id) if r.target_trainer_id else None,
                    "targetUserId": None,
                    "reason": r.reason or None,
                    "apexMemberName": (r.actor.full_name or r.actor.username) if r.actor else None,
                    "createdAt": r.created_at,
                    "targetLabel": r.target_label,
                }
                for r in rows
            ]
        )


class SignupsView(AdminBaseView):
    def get(self, request):
        now = timezone.localtime()
        trainers = Trainer.objects.filter(
            is_superuser=False,
            created_at__year=now.year,
            created_at__month=now.month,
        ).order_by("-created_at")
        out = []
        for trainer in trainers:
            billing = ensure_billing(trainer)
            setup_payment = (
                PlatformPayment.objects.filter(trainer=trainer, kind="setup")
                .order_by("-submitted_at")
                .first()
            )
            status_value = "pending"
            if billing.setup_fee_paid:
                status_value = "approved"
            elif setup_payment and setup_payment.status == "rejected":
                status_value = "rejected"
            out.append(
                {
                    "tinNumber": str(trainer.id),
                    "hotelDisplayName": display_name(trainer),
                    "businessType": "gym",
                    "ownerUserName": trainer.username,
                    "setupFeeETB": _num(billing.setup_fee_etb),
                    "paymentTransactionRef": setup_payment.transaction_ref
                    if setup_payment
                    else None,
                    "paymentChannel": setup_payment.channel if setup_payment else None,
                    "registeredAt": trainer.created_at,
                    "pendingSetupPaymentId": setup_payment.id
                    if setup_payment and setup_payment.status == "pending"
                    else None,
                    "salesAgentId": billing.sales_agent_id,
                    "salesAgentName": billing.sales_agent.name
                    if billing.sales_agent_id
                    else None,
                    "status": status_value,
                    "subscriptionStatus": billing_state(billing),
                }
            )
        return Response(out)


class ChatThreadsView(AdminBaseView):
    def get(self, request):
        limit = min(int(request.query_params.get("limit", 500)), 1000)
        trainers = Trainer.objects.filter(is_superuser=False).order_by("-created_at")[:limit]
        return Response([chat_thread_payload(t) for t in trainers])


class ChatDirectoryView(AdminBaseView):
    def get(self, request):
        search = str(request.query_params.get("search", "")).strip()
        qs = Trainer.objects.filter(is_superuser=False)
        if search:
            qs = qs.filter(
                Q(username__icontains=search)
                | Q(full_name__icontains=search)
                | Q(gym_name__icontains=search)
            )
        out = []
        for trainer in qs[:500]:
            payload = chat_thread_payload(trainer)
            out.append(
                {
                    "tinNumber": payload["tinNumber"],
                    "hotelDisplayName": payload["hotelDisplayName"],
                    "logoUrl": None,
                    "threadId": trainer.id,
                    "chatStatus": "open",
                    "unreadFromTenant": payload["unreadFromTenant"],
                    "updatedAt": payload["updatedAt"],
                    "lastMessage": payload["lastMessage"],
                }
            )
        return Response(out)


class ChatThreadView(AdminBaseView):
    def get(self, request, trainer_id: int):
        trainer = Trainer.objects.filter(pk=trainer_id, is_superuser=False).first()
        if not trainer:
            return Response({"detail": "Trainer not found."}, status=404)
        messages = AdminChatMessage.objects.filter(trainer=trainer).order_by("created_at")
        messages.filter(sender="trainer", admin_read_at__isnull=True).update(
            admin_read_at=timezone.now()
        )
        return Response(
            {
                **chat_thread_payload(trainer),
                "messages": [
                    {
                        "id": m.id,
                        "senderSide": "tenant" if m.sender == "trainer" else "apex",
                        "tenantUserName": display_name(trainer) if m.sender == "trainer" else None,
                        "apexDisplayName": "Apex" if m.sender == "admin" else None,
                        "body": m.body,
                        "imageUrl": m.image_url or (m.media_urls[0] if m.media_urls else None),
                        "createdAt": m.created_at,
                        "isBroadcast": m.is_broadcast,
                    }
                    for m in messages
                ],
            }
        )

    def post(self, request, trainer_id: int):
        trainer = Trainer.objects.filter(pk=trainer_id, is_superuser=False).first()
        if not trainer:
            return Response({"detail": "Trainer not found."}, status=404)
        body = str(request.data.get("body", "")).strip()
        image_url = str(request.data.get("imageUrl", "")).strip()
        if not body and not image_url:
            return Response({"detail": "Message is empty."}, status=400)
        message = AdminChatMessage.objects.create(
            trainer=trainer,
            sender="admin",
            body=body,
            image_url=image_url,
            media_urls=[image_url] if image_url else [],
            admin_read_at=timezone.now(),
        )
        return Response({"id": message.id}, status=201)


class ChatBroadcastView(AdminBaseView):
    def post(self, request):
        body = str(request.data.get("body", "")).strip()
        image_url = str(request.data.get("imageUrl", "")).strip()
        if not body and not image_url:
            return Response({"detail": "Message is empty."}, status=400)
        count = broadcast_to_trainers(self.admin, body, image_url)
        return Response({"sent": count})


class ChatStartView(AdminBaseView):
    def post(self, request):
        trainer_id = request.data.get("trainerId")
        body = str(request.data.get("body", "")).strip()
        trainer = Trainer.objects.filter(pk=trainer_id, is_superuser=False).first()
        if not trainer:
            return Response({"detail": "Trainer not found."}, status=404)
        AdminChatMessage.objects.create(
            trainer=trainer,
            sender="admin",
            body=body,
            admin_read_at=timezone.now(),
        )
        return Response({"threadId": trainer.id}, status=201)
