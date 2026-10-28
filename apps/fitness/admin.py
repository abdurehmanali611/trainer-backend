from django.contrib import admin

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
    PersonalRecord,
    PlannedExercise,
    ProgressPhoto,
    PermissionRequest,
    PushToken,
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


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "email", "mode", "trainer", "is_active", "created_at")
    list_filter = ("mode", "is_active")
    search_fields = ("name", "phone", "email")


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ("client", "date", "time", "status", "trainer")
    list_filter = ("status",)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("client", "amount", "due_date", "status")
    list_filter = ("status",)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("client", "transaction_id", "channel", "status", "created_at")
    list_filter = ("status", "channel")


admin.site.register([SubscriptionPackage, SubscriptionPeriod, Message, Notification,
                     Exercise, WorkoutPlan, DietPlan, Measurement, ProgressPhoto,
                     PersonalRecord, FoodDiaryEntry, WaterLog, RescheduleRequest,
                     PermissionRequest, Achievement, Streak, PushToken])
