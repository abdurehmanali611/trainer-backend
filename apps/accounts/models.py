from django.contrib.auth.models import AbstractUser
from django.db import models


class Trainer(AbstractUser):
    """A subscribed trainer — the SaaS customer. One person = trainer+owner+admin."""

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    gym_name = models.CharField(max_length=150, blank=True)
    # Optional profile photo — doubles as the avatar across the app
    avatar_url = models.URLField(blank=True)

    # Inactive-client alert threshold (customizable per trainer, in days)
    inactive_days_threshold = models.PositiveIntegerField(default=7)

    # Payment instructions shown to clients
    telebirr_number = models.CharField(max_length=64, blank=True)
    bank_name = models.CharField(max_length=120, blank=True)
    bank_account_name = models.CharField(max_length=120, blank=True)
    bank_account_number = models.CharField(max_length=64, blank=True)
    cash_note = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]

    @property
    def push_user_type(self) -> str:
        return "trainer"

    def __str__(self) -> str:
        return self.full_name or self.username
