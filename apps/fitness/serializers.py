from __future__ import annotations

from datetime import date, datetime, timedelta

from rest_framework import serializers

from .models import (
    Achievement,
    Client,
    DietPlan,
    Exercise,
    FoodDiaryEntry,
    Invoice,
    Measurement,
    Meal,
    MealItem,
    Message,
    Notification,
    Payment,
    PaymentInstruction,
    PersonalRecord,
    PlannedExercise,
    ProgressPhoto,
    PermissionRequest,
    RescheduleRequest,
    Session,
    SetLog,
    Streak,
    SubscriptionPackage,
    SubscriptionPeriod,
    WaterLog,
    WorkoutDay,
    WorkoutPlan,
)


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------


class MeasurementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Measurement
        fields = [
            "id", "date", "weight", "body_fat", "chest", "waist", "arms", "thighs",
        ]


class ProgressPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProgressPhoto
        fields = ["id", "url", "date", "note", "created_at"]


class PersonalRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonalRecord
        fields = ["id", "exercise", "weight", "reps", "date"]


class StreakSerializer(serializers.ModelSerializer):
    class Meta:
        model = Streak
        fields = ["current", "longest", "last_activity_date"]


class AchievementSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source="get_key_display", read_only=True)

    class Meta:
        model = Achievement
        fields = ["id", "key", "label", "unlocked_at"]


class ClientListSerializer(serializers.ModelSerializer):
    """Lightweight row for lists & dashboard summaries."""

    last_session_date = serializers.SerializerMethodField()
    access_state = serializers.SerializerMethodField()
    goal_label = serializers.SerializerMethodField()
    payment_instruction = serializers.PrimaryKeyRelatedField(read_only=True)
    payment_instruction_label = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = [
            "id", "name", "phone", "email", "mode", "goals", "current_weight",
            "target_weight", "body_fat", "avatar_url", "is_active", "created_at",
            "last_session_date", "access_state", "goal_label", "must_change_credential",
            "payment_instruction", "payment_instruction_label",
        ]

    def get_last_session_date(self, obj):
        last = (
            obj.sessions.filter(status="completed").order_by("-date").values_list("date", flat=True).first()
        )
        return last.isoformat() if last else None

    def get_access_state(self, obj):
        from .services import client_access_state

        return client_access_state(obj)["state"]

    def get_goal_label(self, obj):
        goals = obj.goals or []
        return ", ".join(goals) if goals else "—"

    def get_payment_instruction_label(self, obj):
        if not obj.payment_instruction_id:
            return None
        return obj.payment_instruction.label


class ClientDetailSerializer(ClientListSerializer):
    measurements = MeasurementSerializer(many=True, read_only=True)
    photos = ProgressPhotoSerializer(many=True, read_only=True)
    records = PersonalRecordSerializer(many=True, read_only=True)
    streak = StreakSerializer(read_only=True)
    achievements = AchievementSerializer(many=True, read_only=True)
    otp = serializers.CharField(read_only=True)

    class Meta(ClientListSerializer.Meta):
        fields = ClientListSerializer.Meta.fields + [
            "otp", "medical_history", "emergency_contact", "must_change_credential",
            "measurements", "photos", "records", "streak", "achievements",
        ]


class ClientCreateSerializer(serializers.ModelSerializer):
    package_id = serializers.IntegerField(required=False, allow_null=True)
    trial_days = serializers.IntegerField(required=False, default=14)
    payment_instruction = serializers.PrimaryKeyRelatedField(
        queryset=PaymentInstruction.objects.all(), required=False, allow_null=True
    )
    otp = serializers.CharField(read_only=True)

    class Meta:
        model = Client
        fields = [
            "id", "name", "phone", "email", "goals", "medical_history",
            "emergency_contact", "current_weight", "target_weight", "body_fat",
            "avatar_url", "package_id", "trial_days", "otp", "payment_instruction",
        ]

    def validate_payment_instruction(self, value):
        if value is not None and value.trainer_id != self.context["request"].user.id:
            raise serializers.ValidationError("That payment instruction is not yours.")
        return value

    def validate_email(self, value):
        trainer = self.context["request"].user
        if Client.objects.filter(trainer=trainer, email__iexact=value).exists():
            raise serializers.ValidationError("A client with this email already exists.")
        return value

    def create(self, validated_data):
        package_id = validated_data.pop("package_id", None)
        trial_days = validated_data.pop("trial_days", 14) or 14
        trainer = self.context["request"].user
        client = Client.objects.create(trainer=trainer, **validated_data)

        today = date.today()
        if client.mode == "illustrative":
            SubscriptionPeriod.objects.create(
                client=client, start_date=today,
                end_date=today + timedelta(days=3650), amount=0,
            )
        elif client.mode == "trial":
            SubscriptionPeriod.objects.create(
                client=client, start_date=today,
                end_date=today + timedelta(days=trial_days), amount=0, is_trial=True,
            )
        else:  # paid
            package = SubscriptionPackage.objects.filter(id=package_id, trainer=trainer).first()
            amount = package.price if package else 0
            end = today + timedelta(days=package.duration_days if package else 30)
            period = SubscriptionPeriod.objects.create(
                client=client, package=package, start_date=today, end_date=end, amount=amount,
            )
            Invoice.objects.create(
                client=client, period=period, amount=amount, due_date=today,
            )
        return client


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------


class ExerciseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Exercise
        fields = [
            "id", "name", "exercise_type", "muscle_group", "difficulty", "equipment",
            "description", "sets", "reps", "rest_seconds", "duration_minutes",
            "video_url", "trainer",
        ]
        read_only_fields = ["id", "trainer"]


class PlannedExerciseSerializer(serializers.ModelSerializer):
    exercise_detail = ExerciseSerializer(source="exercise", read_only=True)

    class Meta:
        model = PlannedExercise
        fields = [
            "id", "exercise", "exercise_detail", "sets", "reps", "target_weight",
            "rest_seconds", "order",
        ]


class WorkoutDaySerializer(serializers.ModelSerializer):
    exercises = PlannedExerciseSerializer(many=True)

    class Meta:
        model = WorkoutDay
        fields = ["id", "day_name", "order", "exercises"]


class WorkoutPlanSerializer(serializers.ModelSerializer):
    days = WorkoutDaySerializer(many=True, required=False)
    client_name = serializers.CharField(source="client.name", read_only=True, default=None)

    class Meta:
        model = WorkoutPlan
        fields = ["id", "name", "description", "client", "client_name", "days", "is_template", "created_at"]
        read_only_fields = ["id", "is_template", "created_at"]

    def create(self, validated_data):
        days_data = validated_data.pop("days", [])
        plan = WorkoutPlan.objects.create(**validated_data)
        self._write_days(plan, days_data)
        return plan

    def update(self, instance, validated_data):
        days_data = validated_data.pop("days", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if days_data is not None:
            instance.days.all().delete()
            self._write_days(instance, days_data)
        return instance

    def _write_days(self, plan, days_data):
        for i, day_data in enumerate(days_data):
            exercises = day_data.pop("exercises", [])
            day = WorkoutDay.objects.create(
                plan=plan, day_name=day_data.get("day_name", f"Day {i + 1}"),
                order=day_data.get("order", i),
            )
            for j, ex in enumerate(exercises):
                PlannedExercise.objects.create(
                    day=day,
                    exercise_id=ex["exercise"],
                    sets=ex.get("sets", 3),
                    reps=ex.get("reps", "10"),
                    target_weight=ex.get("target_weight", 0),
                    rest_seconds=ex.get("rest_seconds", 60),
                    order=ex.get("order", j),
                )


class MealItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = MealItem
        fields = ["id", "name", "calories", "protein", "carbs", "fats", "order"]


class MealSerializer(serializers.ModelSerializer):
    items = MealItemSerializer(many=True)

    class Meta:
        model = Meal
        fields = ["id", "name", "time", "order", "items"]


class DietPlanSerializer(serializers.ModelSerializer):
    meals = MealSerializer(many=True, required=False)
    client_name = serializers.CharField(source="client.name", read_only=True, default=None)

    class Meta:
        model = DietPlan
        fields = [
            "id", "name", "description", "client", "client_name", "daily_calories", "protein",
            "carbs", "fats", "meals", "is_template", "created_at",
        ]
        read_only_fields = ["id", "is_template", "created_at"]

    def create(self, validated_data):
        meals_data = validated_data.pop("meals", [])
        plan = DietPlan.objects.create(**validated_data)
        self._write_meals(plan, meals_data)
        return plan

    def update(self, instance, validated_data):
        meals_data = validated_data.pop("meals", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if meals_data is not None:
            instance.meals.all().delete()
            self._write_meals(instance, meals_data)
        return instance

    def _write_meals(self, plan, meals_data):
        for i, meal_data in enumerate(meals_data):
            items = meal_data.pop("items", [])
            meal = Meal.objects.create(
                diet_plan=plan, name=meal_data.get("name", f"Meal {i + 1}"),
                time=meal_data.get("time", ""), order=meal_data.get("order", i),
            )
            for j, item in enumerate(items):
                MealItem.objects.create(
                    meal=meal, name=item.get("name", ""),
                    calories=item.get("calories", 0), protein=item.get("protein", 0),
                    carbs=item.get("carbs", 0), fats=item.get("fats", 0),
                    order=item.get("order", j),
                )


class FoodDiaryEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = FoodDiaryEntry
        fields = [
            "id", "date", "meal_name", "description", "calories", "photo_url",
            "status", "trainer_feedback", "created_at",
        ]
        read_only_fields = ["id", "status", "trainer_feedback", "created_at"]


class WaterLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = WaterLog
        fields = ["id", "date", "amount_ml", "trainer_feedback", "reviewed"]


class SetLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = SetLog
        fields = [
            "id", "planned_exercise", "exercise_name", "date", "set_index",
            "weight", "reps", "completed", "completed_at",
        ]


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------


class SessionSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.name", read_only=True)
    recommended_workouts = serializers.PrimaryKeyRelatedField(
        queryset=WorkoutPlan.objects.all(), many=True, required=False
    )
    recommended_diets = serializers.PrimaryKeyRelatedField(
        queryset=DietPlan.objects.all(), many=True, required=False
    )
    recommended_workout_names = serializers.SerializerMethodField()
    recommended_diet_names = serializers.SerializerMethodField()

    class Meta:
        model = Session
        fields = [
            "id", "client", "client_name", "date", "time", "end_date", "end_time",
            "duration_minutes",
            "status", "notes", "is_online", "created_at",
            "recommended_workouts", "recommended_diets",
            "recommended_workout_names", "recommended_diet_names",
        ]

    def validate(self, attrs):
        """Keep start → end and duration_minutes in sync.

        - Explicit end given: duration is derived from it (end must be after start).
        - Start moved without an end: end is re-derived from start + duration.
        - Neither given: nothing to do (end stays as stored).
        """
        attrs = super().validate(attrs)
        end_given = "end_date" in attrs or "end_time" in attrs
        start_given = "date" in attrs or "time" in attrs
        if not end_given and not start_given:
            return attrs

        source = attrs if self.instance is None else {**self._snapshot(), **attrs}
        start_date = source.get("date")
        start_time = source.get("time")
        if start_date is None or start_time is None:
            return attrs

        start = datetime.combine(start_date, start_time)
        if end_given:
            end_date = attrs.get("end_date", source.get("end_date"))
            end_time = attrs.get("end_time", source.get("end_time"))
            if end_date is None or end_time is None:
                raise serializers.ValidationError(
                    "Provide both end date and end time, or neither."
                )
            end = datetime.combine(end_date, end_time)
            if end <= start:
                raise serializers.ValidationError(
                    "End date/time must be after the start date/time."
                )
            attrs["duration_minutes"] = max(1, int((end - start).total_seconds() // 60))
        else:
            duration = source.get("duration_minutes") or 60
            end = start + timedelta(minutes=duration)
            attrs["end_date"] = end.date()
            attrs["end_time"] = end.time().replace(microsecond=0)
        return attrs

    def _snapshot(self):
        return {
            "date": self.instance.date,
            "time": self.instance.time,
            "end_date": self.instance.end_date,
            "end_time": self.instance.end_time,
            "duration_minutes": self.instance.duration_minutes,
        }

    def get_recommended_workout_names(self, obj):
        return [plan.name for plan in obj.recommended_workouts.all()]

    def get_recommended_diet_names(self, obj):
        return [plan.name for plan in obj.recommended_diets.all()]


class RescheduleRequestSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.name", read_only=True)
    session_info = serializers.SerializerMethodField()

    class Meta:
        model = RescheduleRequest
        fields = [
            "id", "session", "session_info", "client", "client_name",
            "requested_date", "requested_time", "reason", "status",
            "trainer_note", "created_at", "decided_at",
        ]
        read_only_fields = ["id", "status", "trainer_note", "created_at", "decided_at"]

    def get_session_info(self, obj):
        if not obj.session_id:
            return None
        return {
            "id": obj.session.id,
            "date": obj.session.date.isoformat(),
            "time": obj.session.time.isoformat(),
            "duration_minutes": obj.session.duration_minutes,
        }


class PermissionRequestSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.name", read_only=True)

    class Meta:
        model = PermissionRequest
        fields = [
            "id", "session", "client", "client_name", "date", "kind", "reason",
            "status", "trainer_note", "created_at", "decided_at",
        ]
        read_only_fields = ["id", "status", "trainer_note", "created_at", "decided_at"]


# ---------------------------------------------------------------------------
# Billing
# ---------------------------------------------------------------------------


class SubscriptionPackageSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPackage
        fields = [
            "id", "name", "price", "sessions_per_week", "duration_days",
            "features", "is_active",
        ]


class SubscriptionPeriodSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.name", read_only=True)
    package_name = serializers.CharField(source="package.name", read_only=True, default=None)

    class Meta:
        model = SubscriptionPeriod
        fields = [
            "id", "client", "client_name", "package", "package_name",
            "start_date", "end_date", "amount", "is_trial", "created_at",
        ]


class PaymentSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.name", read_only=True)
    invoice_info = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            "id", "invoice", "invoice_info", "client", "client_name",
            "transaction_id", "channel", "status", "created_at", "decided_at",
            "decision_note",
        ]
        read_only_fields = [
            "id", "status", "created_at", "decided_at", "decision_note", "invoice_info",
        ]

    def get_invoice_info(self, obj):
        return {
            "id": obj.invoice_id,
            "amount": str(obj.invoice.amount),
            "due_date": obj.invoice.due_date.isoformat(),
            "status": obj.invoice.status,
        }


class InvoiceSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.name", read_only=True)
    period_info = serializers.SerializerMethodField()
    payments = PaymentSerializer(many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id", "client", "client_name", "period", "period_info", "amount",
            "due_date", "status", "created_at", "paid_at", "payments",
        ]

    def get_period_info(self, obj):
        if not obj.period_id:
            return None
        return {
            "id": obj.period.id,
            "start_date": obj.period.start_date.isoformat(),
            "end_date": obj.period.end_date.isoformat(),
            "is_trial": obj.period.is_trial,
        }


# ---------------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------------


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Message
        fields = [
            "id", "sender_type", "client", "content", "kind", "media_urls",
            "is_broadcast", "broadcast_id", "trainer_read_at", "client_read_at",
            "created_at",
        ]


class ThreadSerializer(serializers.ModelSerializer):
    last_message = serializers.SerializerMethodField()
    unread = serializers.SerializerMethodField()
    access_state = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = [
            "id", "name", "avatar_url", "last_message", "unread", "access_state",
        ]

    def get_last_message(self, obj):
        msg = obj.messages.order_by("-created_at").first()
        if not msg:
            return None
        return {
            "content": msg.content or ("📷" if msg.kind == "image" else "🎤"),
            "kind": msg.kind,
            "created_at": msg.created_at.isoformat(),
            "sender_type": msg.sender_type,
            "is_broadcast": msg.is_broadcast,
        }

    def get_unread(self, obj):
        return obj.messages.filter(sender_type="client", trainer_read_at__isnull=True).count()

    def get_access_state(self, obj):
        from .services import client_access_state

        return client_access_state(obj)["state"]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id", "title", "body", "type", "data", "read", "created_at",
        ]


class PaymentInstructionSerializer(serializers.ModelSerializer):
    cycle_label = serializers.SerializerMethodField()
    assigned_clients = serializers.SerializerMethodField()

    class Meta:
        model = PaymentInstruction
        fields = [
            "id", "label", "channel", "telebirr_number", "bank_name",
            "bank_account_name", "bank_account_number", "amount", "is_prepayment",
            "billing_cycle", "cycle_from", "cycle_to", "cycle_label",
            "start_ask_days", "grace_days", "is_active", "assigned_clients",
            "created_at",
        ]
        read_only_fields = ["id", "cycle_label", "assigned_clients", "created_at"]

    def get_cycle_label(self, obj) -> str:
        return obj.cycle_label

    def get_assigned_clients(self, obj) -> list[dict]:
        return [
            {"id": client.id, "name": client.name}
            for client in obj.clients.filter(is_active=True).order_by("name")[:25]
        ]
