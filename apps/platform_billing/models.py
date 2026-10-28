from __future__ import annotations

from django.conf import settings
from django.db import models


class PricingPlan(models.Model):
    setup_fee_etb = models.DecimalField(max_digits=12, decimal_places=2, default=15000)
    quarterly_fee_etb = models.DecimalField(max_digits=12, decimal_places=2, default=5000)
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_active", "-updated_at"]

    def __str__(self) -> str:
        return f"Plan {self.setup_fee_etb} / {self.quarterly_fee_etb}"


class TrainerBilling(models.Model):
    STATUS_REASONS = [
        ("suspended", "Suspended"),
        ("banned", "Banned"),
        ("deleted", "Deleted"),
    ]

    trainer = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="platform_billing",
    )
    sales_agent = models.ForeignKey(
        "platform_billing.SalesAgent",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="trainers",
    )
    setup_fee_etb = models.DecimalField(max_digits=12, decimal_places=2, default=15000)
    quarterly_fee_etb = models.DecimalField(max_digits=12, decimal_places=2, default=5000)
    setup_fee_paid = models.BooleanField(default=False)
    setup_channel = models.CharField(max_length=64, blank=True)
    setup_transaction_ref = models.CharField(max_length=120, blank=True)
    setup_submitted_at = models.DateTimeField(null=True, blank=True)
    setup_approved_at = models.DateTimeField(null=True, blank=True)
    free_trial_ends_at = models.DateField(null=True, blank=True)
    paid_until = models.DateField(null=True, blank=True)
    paid_quarters_count = models.PositiveIntegerField(default=0)
    billing_hold = models.BooleanField(default=False)
    is_illustration = models.BooleanField(default=False)
    billing_notes = models.TextField(blank=True)
    billing_started_at = models.DateField(null=True, blank=True)
    account_status = models.CharField(max_length=16, default="active")
    status_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Trainer billing"
        verbose_name_plural = "Trainer billing"

    def __str__(self) -> str:
        return f"Billing for {self.trainer}"


class PlatformPayment(models.Model):
    KINDS = [("setup", "Setup fee"), ("quarterly", "Quarterly fee")]
    STATUSES = [
        ("pending", "Pending approval"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]
    SOURCES = [("self_signup", "Self signup"), ("trainer_app", "Trainer app"), ("admin", "Admin")]

    trainer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="platform_payments",
    )
    kind = models.CharField(max_length=16, choices=KINDS)
    amount_etb = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    channel = models.CharField(max_length=64, blank=True)
    transaction_ref = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=16, choices=STATUSES, default="pending")
    source = models.CharField(max_length=16, choices=SOURCES, default="trainer_app")
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=255, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_platform_payments",
    )
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self) -> str:
        return f"{self.kind} {self.amount_etb} for {self.trainer}"


class SalesAgent(models.Model):
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=32, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class AdminAuditLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="platform_audit_logs",
    )
    action = models.CharField(max_length=120)
    target_trainer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="platform_audit_targets",
    )
    target_label = models.CharField(max_length=255, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action} {self.target_label}"


class AdminChatMessage(models.Model):
    SENDERS = [("trainer", "Trainer"), ("admin", "Admin")]

    trainer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="platform_chat_messages",
    )
    sender = models.CharField(max_length=8, choices=SENDERS)
    body = models.TextField(blank=True)
    image_url = models.URLField(blank=True)
    media_urls = models.JSONField(default=list, blank=True)
    is_broadcast = models.BooleanField(default=False)
    broadcast_id = models.CharField(max_length=40, blank=True, db_index=True)
    trainer_read_at = models.DateTimeField(null=True, blank=True)
    admin_read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.sender}: {self.body[:40]}"
