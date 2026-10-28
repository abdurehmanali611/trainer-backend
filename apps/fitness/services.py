"""Domain logic shared by trainer + internal client endpoints."""
from __future__ import annotations

from datetime import date

from .models import (
    Client,
    Invoice,
    Notification,
    Payment,
    PushToken,
    SubscriptionPeriod,
)
from apps.core.utils import send_expo_push


def client_access_state(client: Client) -> dict:
    """
    Decide whether a client can use the app.

    Returns one of:
      {state: "allowed", ...}
      {state: "blocked_unpaid", invoice: ...}   — expired period with unpaid invoice
      {state: "blocked_no_period"}              — no period covers today (contact trainer)
      {state: "blocked_trial_expired", ...}     — trial over, no paid period
    """
    from datetime import datetime

    today = date.today()

    if client.mode == "illustrative" or not client.is_active:
        return {"state": "allowed", "reason": "illustrative" if client.mode == "illustrative" else "inactive"}

    period = (
        client.periods.filter(start_date__lte=today, end_date__gte=today)
        .order_by("-end_date")
        .first()
    )
    if period:
        if period.is_trial:
            return {"state": "allowed", "reason": "trial", "period_id": period.id}
        invoice = period.invoices.order_by("-created_at").first()
        if invoice is None:
            return {"state": "allowed", "reason": "no_invoice", "period_id": period.id}
        if invoice.status in ("paid", "forgiven"):
            return {"state": "allowed", "reason": "paid", "period_id": period.id}
        # Still inside the pay window (start..end) — allowed while they pay
        if today <= period.end_date:
            return {
                "state": "allowed",
                "reason": "pay_window",
                "period_id": period.id,
                "invoice_id": invoice.id,
            }
        return {
            "state": "blocked_unpaid",
            "invoice_id": invoice.id,
            "period_id": period.id,
        }

    # Grace window — the payment instruction can keep the app open for a few
    # days after the final day of the subscription before blocking.
    grace = 0
    if client.payment_instruction_id:
        grace = client.payment_instruction.grace_days or 0
    last_period = client.periods.order_by("-end_date").first()
    if grace and last_period:
        from datetime import timedelta

        if today <= last_period.end_date + timedelta(days=grace):
            return {
                "state": "allowed",
                "reason": "grace",
                "period_id": last_period.id,
            }

    # No period covers today
    unpaid = (
        client.invoices.filter(status__in=("pending", "overdue")).order_by("-due_date").first()
    )
    if unpaid:
        return {"state": "blocked_unpaid", "invoice_id": unpaid.id}
    return {"state": "blocked_no_period"}


def payment_instruction_payload(trainer) -> dict:
    return {
        "telebirr_number": trainer.telebirr_number,
        "bank_name": trainer.bank_name,
        "bank_account_name": trainer.bank_account_name,
        "bank_account_number": trainer.bank_account_number,
        "cash_note": trainer.cash_note,
    }


def mark_overdue_invoices():
    """Management-friendly helper: flip pending invoices past due to overdue."""
    today = date.today()
    Invoice.objects.filter(status="pending", due_date__lt=today).update(status="overdue")


def notify_client(client: Client, title: str, body: str, ntype: str = "alert", data: dict | None = None):
    Notification.objects.create(
        target="client", user_id=client.id, title=title, body=body,
        type=ntype, data=data or {},
    )
    tokens = list(
        PushToken.objects.filter(user_type="client", user_id=client.id).values_list("token", flat=True)
    )
    send_expo_push(tokens, title, body, {"type": ntype, **(data or {})})


def notify_trainer(trainer, title: str, body: str, ntype: str = "alert", data: dict | None = None):
    Notification.objects.create(
        target="trainer", user_id=trainer.id, title=title, body=body,
        type=ntype, data=data or {},
    )
    tokens = list(
        PushToken.objects.filter(user_type="trainer", user_id=trainer.id).values_list("token", flat=True)
    )
    send_expo_push(tokens, title, body, {"type": ntype, **(data or {})})


def approve_payment(payment: Payment, channel: str | None = None, note: str = ""):
    from django.utils import timezone

    payment.status = "approved"
    payment.decided_at = timezone.now()
    if channel:
        payment.channel = channel
    if note:
        payment.decision_note = note
    payment.save()

    invoice = payment.invoice
    invoice.status = "paid"
    invoice.paid_at = timezone.now()
    invoice.save(update_fields=["status", "paid_at"])

    notify_client(
        payment.client,
        "Payment approved",
        f"Your payment {payment.transaction_id} was approved. Access is unlocked.",
        ntype="payment",
        data={"invoice_id": invoice.id},
    )
    return payment


def reject_payment(payment: Payment, note: str = ""):
    from django.utils import timezone

    payment.status = "rejected"
    payment.decided_at = timezone.now()
    if note:
        payment.decision_note = note
    payment.save()
    notify_client(
        payment.client,
        "Payment rejected",
        note or "Your payment could not be verified. Please contact your trainer.",
        ntype="payment",
    )
    return payment


def forgive_invoice(invoice: Invoice, note: str = ""):
    from django.utils import timezone

    invoice.status = "forgiven"
    invoice.paid_at = timezone.now()
    invoice.save(update_fields=["status", "paid_at"])
    Payment.objects.filter(invoice=invoice, status="pending").update(
        status="forgiven", decided_at=timezone.now(), decision_note=note or "Forgiven by trainer"
    )
    notify_client(
        invoice.client,
        "Payment forgiven",
        "Your trainer waived this subscription payment. You have full access.",
        ntype="payment",
        data={"invoice_id": invoice.id},
    )
    return invoice


def transfer_invoice_period(invoice: Invoice, target_period: SubscriptionPeriod):
    """Move an (already paid/forgiven) invoice's payment to another period,
    e.g. September's payment applied to October."""
    old_period_id = invoice.period_id
    invoice.period = target_period
    invoice.due_date = target_period.start_date
    invoice.amount = target_period.amount or invoice.amount
    invoice.save(update_fields=["period", "due_date", "amount"])
    # Keep target period's amount in sync with what was actually paid
    return {"old_period_id": old_period_id, "new_period_id": target_period.id}


def client_payment_payload(client: Client) -> dict:
    """Access + billing snapshot used by the client app lock screen & billing tab."""
    from apps.accounts.models import Trainer

    access = client_access_state(client)
    trainer = client.trainer
    invoice_data = None
    if access.get("invoice_id"):
        invoice = Invoice.objects.filter(id=access["invoice_id"]).first()
    elif access.get("state") == "blocked_unpaid":
        invoice = client.invoices.filter(status__in=("pending", "overdue")).first()
    else:
        invoice = None
    if invoice:
        period = invoice.period
        invoice_data = {
            "id": invoice.id,
            "amount": str(invoice.amount),
            "status": invoice.status,
            "due_date": invoice.due_date.isoformat(),
            "period": (
                {
                    "id": period.id,
                    "start_date": period.start_date.isoformat(),
                    "end_date": period.end_date.isoformat(),
                }
                if period
                else None
            ),
        }
    active_period = (
        client.periods.filter(start_date__lte=date.today(), end_date__gte=date.today())
        .order_by("-end_date")
        .first()
    )
    return {
        "access": access,
        "invoice": invoice_data,
        "active_period": (
            {
                "id": active_period.id,
                "start_date": active_period.start_date.isoformat(),
                "end_date": active_period.end_date.isoformat(),
                "is_trial": active_period.is_trial,
                "amount": str(active_period.amount),
                "package_name": active_period.package.name if active_period.package else None,
            }
            if active_period
            else None
        ),
        "payment_instructions": payment_instruction_payload(trainer),
        "mode": client.mode,
    }


def assert_within_trainer(client: Client, trainer) -> None:
    if client.trainer_id != trainer.id:
        from rest_framework.exceptions import NotFound

        raise NotFound("Client not found.")
