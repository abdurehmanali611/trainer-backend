from django.contrib import admin

from .models import Trainer


@admin.register(Trainer)
class TrainerAdmin(admin.ModelAdmin):
    list_display = ("username", "email", "full_name", "gym_name", "created_at")
    search_fields = ("username", "email", "full_name")
