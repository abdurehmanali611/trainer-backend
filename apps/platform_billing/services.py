from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from .models import (
    AdminAuditLog,
    AdminChatMessage,
    PlatformPayment,
    PricingPlan,
    TrainerBilling,
)

QUARTER_DAYS = 90
PAYMENT_WINDOW_DAYS = 5
TRIAL_NOTICE_DAYS = 7
DEFAULT_SETUP_FEE = Decimal("15000")
DEFAULT_QUARTERLY_FEE = Decimal("5000")

ALLOWED_STATES = {"trial", "trial_ending", "active", "warning", "exempt"}


def active_plan() -> PricingPlan | None:
    return PricingPlan.objects.filter(is_active=True).order_by("-updated_at").first()


def plan_fees() -> tuple[Decimal, Decimal]:
    plan = active_plan()
    if plan:
        return plan.setup_fee_etb, plan.quarterly_fee_etb
    return DEFAULT_SETUP_FEE, DEFAULT_QUARTERLY_FEE


def ensure_billing(trainer) -> TrainerBilling:
    billing, created = TrainerBilling.objects.get_or_create(trainer=trainer)
    if created:
        setup_fee, quarterly_fee = plan_fees()
        billing.setup_fee_etb = setup_fee
        billing.quarterly_fee_etb = quarterly_fee
        billing.save(update_fields=["setup_fee_etb", "quarterly_fee_etb"])
    return billing


def today() -> date:
    return timezone.localdate()


def billing_state(billing: TrainerBilling, on: date | None = None) -> str:
    on = on or today()
    if billing.trainer.is_superuser:
        return "exempt"
    if billing.is_illustration:
        return "exempt"
    if billing.account_status in ("deleted",):
        return "deleted"
    if billing.account_status in ("banned", "suspended"):
        return billing.account_status
    if billing.billing_hold:
        return "on_hold"
    if billing.free_trial_ends_at and on < billing.free_trial_ends_at:
        remaining = (billing.free_trial_ends_at - on).days
        return "trial_ending" if remaining <= TRIAL_NOTICE_DAYS else "trial"
    if not billing.setup_fee_paid:
        pending = PlatformPayment.objects.filter(
            trainer=billing.trainer, kind="setup", status="pending"
        ).exists()
        return "setup_pending" if pending else "setup_required"
    if billing.paid_until and on <= billing.paid_until:
        remaining = (billing.paid_until - on).days
        return "active" if remaining > PAYMENT_WINDOW_DAYS else "warning"
    return "expired"


def is_allowed(billing: TrainerBilling) -> bool:
    return billing_state(billing) in ALLOWED_STATES


def days_remaining(billing: TrainerBilling, on: date | None = None) -> int | None:
    on = on or today()
    if billing.free_trial_ends_at and on < billing.free_trial_ends_at:
        return (billing.free_trial_ends_at - on).days
    if billing.paid_until:
        return (billing.paid_until - on).days
    return None


def window_opens_on(billing: TrainerBilling) -> date | None:
    if not billing.paid_until:
        return None
    return billing.paid_until - timedelta(days=PAYMENT_WINDOW_DAYS)


def can_submit_quarterly(billing: TrainerBilling, on: date | None = None) -> bool:
    on = on or today()
    if billing.is_illustration or billing.billing_hold:
        return False
    if not billing.setup_fee_paid:
        return False
    if billing.account_status != "active":
        return False
    if not billing.paid_until:
        return True
    return on >= billing.paid_until - timedelta(days=PAYMENT_WINDOW_DAYS)


def pending_payment(billing: TrainerBilling, kind: str) -> PlatformPayment | None:
    return (
        PlatformPayment.objects.filter(trainer=billing.trainer, kind=kind, status="pending")
        .order_by("-submitted_at")
        .first()
    )


def notices(billing: TrainerBilling, on: date | None = None) -> list[dict]:
    on = on or today()
    state = billing_state(billing, on)
    out: list[dict] = []
    if state == "trial_ending" and billing.free_trial_ends_at:
        left = (billing.free_trial_ends_at - on).days
        out.append(
            {
                "id": "trial-ending",
                "severity": "warning",
                "title": f"Free trial ends in {left} day{'s' if left != 1 else ''}",
                "message": "Your free trial is ending soon. Review your subscription in Billing.",
            }
        )
    if state == "warning" and billing.paid_until:
        left = (billing.paid_until - on).days
        out.append(
            {
                "id": "renewal-window",
                "severity": "warning",
                "title": "Quarterly payment window is open",
                "message": f"Your current quarter ends in {left} day{'s' if left != 1 else ''}. Submit your payment reference before it ends to keep access.",
            }
        )
    if state == "expired":
        out.append(
            {
                "id": "expired",
                "severity": "critical",
                "title": "Quarterly payment required",
                "message": "Your subscription has ended. Submit a quarterly payment reference to restore access.",
            }
        )
    if state == "setup_pending":
        out.append(
            {
                "id": "setup-pending",
                "severity": "critical",
                "title": "Setup fee awaiting approval",
                "message": "Your setup payment is being verified. Access starts as soon as it is approved.",
            }
        )
    if state == "setup_required":
        out.append(
            {
                "id": "setup-required",
                "severity": "critical",
                "title": "Setup fee required",
                "message": "Submit your setup fee payment reference to activate your account.",
            }
        )
    if state == "on_hold":
        out.append(
            {
                "id": "billing-hold",
                "severity": "critical",
                "title": "Billing hold",
                "message": "Your account is on billing hold. Contact support to restore access.",
            }
        )
    return out


def billing_payload(billing: TrainerBilling) -> dict:
    setup_fee, quarterly_fee = plan_fees()
    state = billing_state(billing)
    setup_pending = pending_payment(billing, "setup")
    quarterly_pending = pending_payment(billing, "quarterly")
    return {
        "state": state,
        "allowed": state in ALLOWED_STATES,
        "setup_fee_etb": float(billing.setup_fee_etb or setup_fee),
        "quarterly_fee_etb": float(billing.quarterly_fee_etb or quarterly_fee),
        "setup_fee_paid": billing.setup_fee_paid,
        "free_trial_ends_at": billing.free_trial_ends_at,
        "paid_until": billing.paid_until,
        "billing_started_at": billing.billing_started_at,
        "paid_quarters_count": billing.paid_quarters_count,
        "billing_hold": billing.billing_hold,
        "is_illustration": billing.is_illustration,
        "days_remaining": days_remaining(billing),
        "window_opens_on": window_opens_on(billing),
        "can_submit_payment": can_submit_quarterly(billing),
        "pending_payment": _payment_payload(setup_pending or quarterly_pending),
        "notices": notices(billing),
    }


def _payment_payload(payment: PlatformPayment | None) -> dict | None:
    if not payment:
        return None
    return {
        "id": payment.id,
        "kind": payment.kind,
        "status": payment.status,
        "amount_etb": float(payment.amount_etb),
        "channel": payment.channel,
        "transaction_ref": payment.transaction_ref,
        "submitted_at": payment.submitted_at,
        "review_note": payment.review_note,
    }


def create_setup_payment(
    trainer,
    channel: str,
    transaction_ref: str,
    source: str = "self_signup",
) -> PlatformPayment:
    billing = ensure_billing(trainer)
    setup_fee, _ = plan_fees()
    payment = PlatformPayment.objects.create(
        trainer=trainer,
        kind="setup",
        amount_etb=billing.setup_fee_etb or setup_fee,
        channel=channel.strip(),
        transaction_ref=transaction_ref.strip(),
        source=source,
    )
    billing.setup_channel = payment.channel
    billing.setup_transaction_ref = payment.transaction_ref
    billing.setup_submitted_at = payment.submitted_at
    billing.save(
        update_fields=["setup_channel", "setup_transaction_ref", "setup_submitted_at"]
    )
    return payment


def submit_quarterly_payment(trainer, channel: str, transaction_ref: str) -> PlatformPayment:
    billing = ensure_billing(trainer)
    if not can_submit_quarterly(billing):
        raise ValueError("The quarterly payment window is not open yet.")
    if PlatformPayment.objects.filter(
        trainer=trainer, kind="quarterly", status="pending"
    ).exists():
        raise ValueError("A quarterly payment is already waiting for approval.")
    _, quarterly_fee = plan_fees()
    return PlatformPayment.objects.create(
        trainer=trainer,
        kind="quarterly",
        amount_etb=billing.quarterly_fee_etb or quarterly_fee,
        channel=channel.strip(),
        transaction_ref=transaction_ref.strip(),
        source="trainer_app",
    )


def add_months_quarters(start: date, quarters: int = 1) -> date:
    return start + timedelta(days=QUARTER_DAYS * quarters)


def approve_payment(payment: PlatformPayment, reviewer=None) -> PlatformPayment:
    billing = ensure_billing(payment.trainer)
    on = today()
    if payment.kind == "setup":
        billing.setup_fee_paid = True
        billing.setup_approved_at = timezone.now()
        if not billing.billing_started_at:
            billing.billing_started_at = on
        if not billing.paid_until:
            billing.paid_until = add_months_quarters(on)
    else:
        base = billing.paid_until or on
        billing.paid_until = add_months_quarters(base)
        billing.paid_quarters_count += 1
        payment.period_start = base
        payment.period_end = billing.paid_until
        if not billing.billing_started_at:
            billing.billing_started_at = on
    payment.status = "approved"
    payment.reviewed_at = timezone.now()
    payment.reviewed_by = reviewer
    payment.save()
    billing.save()
    return payment


def reject_payment(payment: PlatformPayment, reason: str, reviewer=None) -> PlatformPayment:
    payment.status = "rejected"
    payment.review_note = reason.strip()
    payment.reviewed_at = timezone.now()
    payment.reviewed_by = reviewer
    payment.save()
    billing = ensure_billing(payment.trainer)
    if payment.kind == "setup":
        billing.setup_channel = ""
        billing.setup_transaction_ref = ""
        billing.setup_submitted_at = None
        billing.save(
            update_fields=["setup_channel", "setup_transaction_ref", "setup_submitted_at"]
        )
    return payment


def set_trial_end(trainer, trial_end: date | None) -> TrainerBilling:
    billing = ensure_billing(trainer)
    billing.free_trial_ends_at = trial_end
    if trial_end and billing.setup_fee_paid:
        billing.paid_until = add_months_quarters(trial_end)
        if not billing.billing_started_at:
            billing.billing_started_at = trial_end
    billing.save()
    return billing


def log_action(actor, action: str, trainer=None, reason: str = "", label: str = "") -> None:
    AdminAuditLog.objects.create(
        actor=actor,
        action=action,
        target_trainer=trainer,
        target_label=label or (str(trainer) if trainer else ""),
        reason=reason,
    )


def chat_thread_payload(trainer, messages=None) -> dict:
    from apps.accounts.models import Trainer

    billing = ensure_billing(trainer)
    qs = AdminChatMessage.objects.filter(trainer=trainer)
    unread = qs.filter(sender="trainer", admin_read_at__isnull=True).count()
    last = qs.order_by("-created_at").first()
    return {
        "id": trainer.id,
        "tinNumber": str(trainer.id),
        "hotelDisplayName": display_name(trainer),
        "status": "open",
        "unreadFromTenant": unread,
        "updatedAt": (last.created_at if last else trainer.created_at),
        "lastMessage": (
            {
                "body": last.body or ("[image]" if last.image_url else ""),
                "senderSide": "tenant" if last.sender == "trainer" else "apex",
                "createdAt": last.created_at,
            }
            if last
            else None
        ),
        "subscriptionStatus": billing_state(billing),
    }


def display_name(trainer) -> str:
    return trainer.gym_name or trainer.full_name or trainer.username


def broadcast_to_trainers(actor, body: str, image_url: str = "") -> int:
    from apps.accounts.models import Trainer

    broadcast_id = uuid.uuid4().hex[:16]
    trainers = Trainer.objects.filter(is_superuser=False, is_active=True)
    created = 0
    for trainer in trainers:
        AdminChatMessage.objects.create(
            trainer=trainer,
            sender="admin",
            body=body,
            image_url=image_url,
            is_broadcast=True,
            broadcast_id=broadcast_id,
        )
        created += 1
    log_action(actor, "chat.broadcast", label=f"{created} trainers")
    return created
