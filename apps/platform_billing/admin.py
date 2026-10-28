from django.contrib import admin

from .models import (
    AdminAuditLog,
    AdminChatMessage,
    PlatformPayment,
    PricingPlan,
    SalesAgent,
    TrainerBilling,
)

admin.site.register(TrainerBilling)
admin.site.register(PlatformPayment)
admin.site.register(PricingPlan)
admin.site.register(SalesAgent)
admin.site.register(AdminAuditLog)
admin.site.register(AdminChatMessage)
