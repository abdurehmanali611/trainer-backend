"""Fitness domain models — trainer's SaaS workspace data."""
from __future__ import annotations

import secrets

from django.conf import settings
from django.db import models

# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------


def generate_unique_otp() -> str:
    from apps.fitness.models import Client

    for _ in range(50):
        otp = f"{secrets.randbelow(10**6):06d}"
        if not Client.objects.filter(otp=otp).exists():
            return otp
    return f"{secrets.randbelow(10**6):06d}"


class Client(models.Model):
    MODE_CHOICES = [
        ("paid", "Paid subscription"),
        ("trial", "Free trial"),
        ("illustrative", "Illustrative (free forever)"),
    ]

    trainer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="clients"
    )
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=32)
    email = models.EmailField()
    # 6-digit OTP, unique across ALL trainers' clients; client logs in with it
    # until they change it to their own credential on first login.
    otp = models.CharField(max_length=6, unique=True, default=generate_unique_otp)
    credential = models.CharField(max_length=128, blank=True)
    must_change_credential = models.BooleanField(default=True)

    mode = models.CharField(max_length=16, choices=MODE_CHOICES, default="paid")
    goals = models.JSONField(default=list, blank=True)
    medical_history = models.TextField(blank=True)
    emergency_contact = models.CharField(max_length=255, blank=True)
    current_weight = models.FloatField(null=True, blank=True)
    target_weight = models.FloatField(null=True, blank=True)
    body_fat = models.FloatField(null=True, blank=True)
    avatar_url = models.URLField(blank=True)
    payment_instruction = models.ForeignKey(
        "PaymentInstruction",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="clients",
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def push_user_type(self) -> str:
        return "client"

    @property
    def effective_credential(self) -> str:
        return self.credential or self.otp

    def __str__(self) -> str:
        return f"{self.name} ({self.phone})"


class Measurement(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="measurements")
    date = models.DateField()
    weight = models.FloatField(null=True, blank=True)
    body_fat = models.FloatField(null=True, blank=True)
    chest = models.FloatField(null=True, blank=True)
    waist = models.FloatField(null=True, blank=True)
    arms = models.FloatField(null=True, blank=True)
    thighs = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["date"]
        unique_together = [("client", "date")]


class ProgressPhoto(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="photos")
    url = models.URLField()
    date = models.DateField()
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]


class PersonalRecord(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="records")
    exercise = models.CharField(max_length=150)
    weight = models.FloatField()
    reps = models.PositiveIntegerField(default=1)
    date = models.DateField()

    class Meta:
        ordering = ["-date"]
        unique_together = [("client", "exercise")]


class PushToken(models.Model):
    USER_TYPES = [("trainer", "Trainer"), ("client", "Client")]
    user_type = models.CharField(max_length=16, choices=USER_TYPES)
    user_id = models.PositiveIntegerField()
    token = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user_type", "user_id")]


class Achievement(models.Model):
    KEYS = [
        ("first_workout", "First workout completed"),
        ("ten_workouts", "10 workouts completed"),
        ("fifty_workouts", "50 workouts completed"),
        ("streak_7", "7-day streak"),
        ("streak_30", "30-day streak"),
        ("first_weight_log", "First weight logged"),
        ("first_photo", "First progress photo"),
        ("perfect_week", "Completed every planned workout this week"),
    ]
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="achievements")
    key = models.CharField(max_length=32, choices=KEYS)
    unlocked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("client", "key")]
        ordering = ["-unlocked_at"]


class Streak(models.Model):
    client = models.OneToOneField(Client, on_delete=models.CASCADE, related_name="streak")
    current = models.PositiveIntegerField(default=0)
    longest = models.PositiveIntegerField(default=0)
    last_activity_date = models.DateField(null=True, blank=True)

    def register_activity(self, day) -> list[Achievement]:
        """Register activity for `day`; returns newly unlocked achievements."""
        from datetime import timedelta

        new_achievements = []
        streak, _ = Streak.objects.get_or_create(client=self.client)
        if streak.last_activity_date == day:
            return new_achievements
        if streak.last_activity_date == day - timedelta(days=1):
            streak.current += 1
        else:
            streak.current = 1
        streak.longest = max(streak.longest, streak.current)
        streak.last_activity_date = day
        streak.save()

        for threshold, key in ((7, "streak_7"), (30, "streak_30")):
            if streak.current >= threshold:
                ach, created = Achievement.objects.get_or_create(
                    client=self.client, key=key
                )
                if created:
                    new_achievements.append(ach)
        return new_achievements


# ---------------------------------------------------------------------------
# Workout plans
# ---------------------------------------------------------------------------


class Exercise(models.Model):
    MUSCLE_GROUPS = [
        ("Chest", "Chest"), ("Back", "Back"), ("Legs", "Legs"),
        ("Shoulders", "Shoulders"), ("Arms", "Arms"), ("Core", "Core"),
        ("Cardio", "Cardio"),
    ]
    DIFFICULTIES = [
        ("beginner", "Beginner"), ("intermediate", "Intermediate"),
        ("advanced", "Advanced"),
    ]
    TYPES = [
        ("strength", "Strength"), ("cardio", "Cardio"), ("core", "Core"),
        ("flexibility", "Flexibility"), ("mobility", "Mobility"),
        ("plyometrics", "Plyometrics"), ("other", "Other"),
    ]

    trainer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.CASCADE, related_name="exercises",
    )  # null = shared/base library entry
    name = models.CharField(max_length=150)
    exercise_type = models.CharField(max_length=24, choices=TYPES, default="strength")
    muscle_group = models.CharField(max_length=32, choices=MUSCLE_GROUPS)
    difficulty = models.CharField(max_length=16, choices=DIFFICULTIES, default="beginner")
    equipment = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    sets = models.PositiveIntegerField(default=3)
    reps = models.CharField(max_length=32, default="10-12")
    rest_seconds = models.PositiveIntegerField(default=60)
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    video_url = models.URLField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class WorkoutPlan(models.Model):
    trainer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="workout_plans"
    )
    client = models.ForeignKey(
        Client, null=True, blank=True, on_delete=models.CASCADE, related_name="workout_plans"
    )  # null = template
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    @property
    def is_template(self) -> bool:
        return self.client_id is None


class WorkoutDay(models.Model):
    plan = models.ForeignKey(WorkoutPlan, on_delete=models.CASCADE, related_name="days")
    day_name = models.CharField(max_length=50)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]
        unique_together = [("plan", "day_name")]


class PlannedExercise(models.Model):
    day = models.ForeignKey(WorkoutDay, on_delete=models.CASCADE, related_name="exercises")
    exercise = models.ForeignKey(Exercise, on_delete=models.PROTECT)
    sets = models.PositiveIntegerField(default=3)
    reps = models.CharField(max_length=32, default="10")
    target_weight = models.FloatField(default=0)
    rest_seconds = models.PositiveIntegerField(default=60)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]


class SetLog(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="set_logs")
    planned_exercise = models.ForeignKey(
        PlannedExercise, null=True, blank=True, on_delete=models.SET_NULL
    )
    exercise_name = models.CharField(max_length=150)
    date = models.DateField()
    set_index = models.PositiveIntegerField(default=1)
    weight = models.FloatField(default=0)
    reps = models.PositiveIntegerField(default=0)
    completed = models.BooleanField(default=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-date", "set_index"]


# ---------------------------------------------------------------------------
# Diet plans & client food diary
# ---------------------------------------------------------------------------


class DietPlan(models.Model):
    trainer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="diet_plans"
    )
    client = models.ForeignKey(
        Client, null=True, blank=True, on_delete=models.CASCADE, related_name="diet_plans"
    )  # null = template
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True, default="")
    daily_calories = models.PositiveIntegerField(default=2000)
    protein = models.PositiveIntegerField(default=150)
    carbs = models.PositiveIntegerField(default=200)
    fats = models.PositiveIntegerField(default=60)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_template(self) -> bool:
        return self.client_id is None


class Meal(models.Model):
    diet_plan = models.ForeignKey(DietPlan, on_delete=models.CASCADE, related_name="meals")
    name = models.CharField(max_length=100)
    time = models.CharField(max_length=32, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]


class MealItem(models.Model):
    meal = models.ForeignKey(Meal, on_delete=models.CASCADE, related_name="items")
    name = models.CharField(max_length=120)
    calories = models.PositiveIntegerField(default=0)
    protein = models.FloatField(default=0)
    carbs = models.FloatField(default=0)
    fats = models.FloatField(default=0)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]


class FoodDiaryEntry(models.Model):
    STATUS = [("pending", "Pending review"), ("reviewed", "Reviewed")]

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="food_entries")
    date = models.DateField()
    meal_name = models.CharField(max_length=120)
    description = models.TextField()
    calories = models.PositiveIntegerField(null=True, blank=True)
    photo_url = models.URLField(blank=True)
    status = models.CharField(max_length=16, choices=STATUS, default="pending")
    trainer_feedback = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-created_at"]


class WaterLog(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="water_logs")
    date = models.DateField()
    amount_ml = models.PositiveIntegerField(default=0)
    trainer_feedback = models.TextField(blank=True)
    reviewed = models.BooleanField(default=False)

    class Meta:
        ordering = ["-date"]
        unique_together = [("client", "date")]


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------


class Session(models.Model):
    STATUS = [
        ("scheduled", "Scheduled"),
        ("completed", "Completed"),
        ("canceled", "Canceled"),
        ("no_show", "No-show"),
    ]
    trainer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sessions"
    )
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="sessions")
    date = models.DateField()
    time = models.TimeField()
    # Explicit end of the session (start date/time → end date/time).
    end_date = models.DateField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(default=60)
    status = models.CharField(max_length=16, choices=STATUS, default="scheduled")
    notes = models.TextField(blank=True)
    is_online = models.BooleanField(default=False)
    recommended_workouts = models.ManyToManyField(
        WorkoutPlan, blank=True, related_name="session_recommendations"
    )
    recommended_diets = models.ManyToManyField(
        DietPlan, blank=True, related_name="session_recommendations"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "time"]
        unique_together = [("trainer", "date", "time")]


class RescheduleRequest(models.Model):
    STATUS = [("pending", "Pending"), ("approved", "Approved"), ("declined", "Declined")]
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="reschedule_requests")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="reschedule_requests")
    requested_date = models.DateField()
    requested_time = models.TimeField(null=True, blank=True)
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=STATUS, default="pending")
    trainer_note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)


class PermissionRequest(models.Model):
    KIND = [("late", "Late"), ("absent", "Absent")]
    STATUS = [("pending", "Pending"), ("approved", "Approved"), ("declined", "Declined")]
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="permission_requests")
    session = models.ForeignKey(
        Session, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="permission_requests",
    )
    date = models.DateField()
    kind = models.CharField(max_length=8, choices=KIND)
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=STATUS, default="pending")
    trainer_note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)


# ---------------------------------------------------------------------------
# Billing
# ---------------------------------------------------------------------------


class PaymentInstruction(models.Model):
    """A reusable way for a trainer to collect payment.

    Trainers can create several and assign one to each client at creation time.
    Illustrative (non-payable) clients get none.
    """

    CHANNELS = [("telebirr", "Telebirr"), ("bank", "Bank transfer"), ("cash", "Cash")]
    CYCLES = [
        ("monthly", "Monthly"),
        ("quarterly", "Quarterly"),
        ("half_yearly", "Half a year"),
        ("yearly", "Yearly"),
        ("custom", "Custom range"),
    ]

    trainer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payment_instructions"
    )
    label = models.CharField(max_length=120)
    channel = models.CharField(max_length=16, choices=CHANNELS, default="telebirr")
    telebirr_number = models.CharField(max_length=32, blank=True)
    bank_name = models.CharField(max_length=120, blank=True)
    bank_account_name = models.CharField(max_length=150, blank=True)
    bank_account_number = models.CharField(max_length=64, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    # When the money is requested: at the start of the period or at the end.
    is_prepayment = models.BooleanField(default=True)
    billing_cycle = models.CharField(max_length=16, choices=CYCLES, default="monthly")
    cycle_from = models.DateField(null=True, blank=True)
    cycle_to = models.DateField(null=True, blank=True)
    # Ask the client to pay & send the transaction id this many days BEFORE the
    # period ends…
    start_ask_days = models.PositiveIntegerField(default=0)
    # …and keep the app open this many days AFTER the final day, then block.
    grace_days = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def cycle_label(self) -> str:
        if self.billing_cycle == "custom" and self.cycle_from and self.cycle_to:
            days = (self.cycle_to - self.cycle_from).days + 1
            return f"{days} day subscription"
        return dict(self.CYCLES).get(self.billing_cycle, self.billing_cycle)

    def __str__(self) -> str:
        return self.label


class SubscriptionPackage(models.Model):
    trainer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="packages"
    )
    name = models.CharField(max_length=120)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    sessions_per_week = models.PositiveIntegerField(default=3)
    duration_days = models.PositiveIntegerField(default=30)
    features = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["price"]


class SubscriptionPeriod(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="periods")
    package = models.ForeignKey(
        SubscriptionPackage, null=True, blank=True, on_delete=models.SET_NULL
    )
    start_date = models.DateField()
    end_date = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_trial = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]

    def overlaps_today(self) -> bool:
        from datetime import date

        today = date.today()
        return self.start_date <= today <= self.end_date


class Invoice(models.Model):
    STATUS = [
        ("pending", "Pending"),
        ("paid", "Paid"),
        ("overdue", "Overdue"),
        ("forgiven", "Forgiven"),
    ]
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="invoices")
    period = models.ForeignKey(
        SubscriptionPeriod, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="invoices",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    due_date = models.DateField()
    status = models.CharField(max_length=16, choices=STATUS, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class Payment(models.Model):
    CHANNELS = [("cash", "Cash"), ("bank", "Bank"), ("telebirr", "Telebirr")]
    STATUS = [
        ("pending", "Pending approval"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("forgiven", "Forgiven"),
    ]
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="payments")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="payments")
    transaction_id = models.CharField(max_length=120)
    channel = models.CharField(max_length=16, choices=CHANNELS, default="telebirr")
    status = models.CharField(max_length=16, choices=STATUS, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]


# ---------------------------------------------------------------------------
# Messaging & notifications
# ---------------------------------------------------------------------------


class Message(models.Model):
    KINDS = [("text", "Text"), ("image", "Image"), ("voice", "Voice note")]
    sender_type = models.CharField(max_length=8)  # trainer | client
    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, related_name="messages"
    )  # thread owner
    content = models.TextField(blank=True)
    kind = models.CharField(max_length=8, choices=KINDS, default="text")
    media_urls = models.JSONField(default=list, blank=True)
    is_broadcast = models.BooleanField(default=False)
    broadcast_id = models.CharField(max_length=40, blank=True, db_index=True)
    trainer_read_at = models.DateTimeField(null=True, blank=True)
    client_read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class Notification(models.Model):
    TARGETS = [("trainer", "Trainer"), ("client", "Client")]
    TYPES = [
        ("booking", "Booking"), ("payment", "Payment"), ("message", "Message"),
        ("alert", "Alert"), ("achievement", "Achievement"), ("request", "Request"),
    ]
    target = models.CharField(max_length=8, choices=TARGETS)
    # trainer: user id; client: client id
    user_id = models.PositiveIntegerField()
    title = models.CharField(max_length=150)
    body = models.CharField(max_length=255)
    type = models.CharField(max_length=16, choices=TYPES, default="alert")
    data = models.JSONField(default=dict, blank=True)
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
