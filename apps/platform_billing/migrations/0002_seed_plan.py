from decimal import Decimal

from django.db import migrations


def seed_plan(apps, schema_editor):
    PricingPlan = apps.get_model("platform_billing", "PricingPlan")
    if not PricingPlan.objects.exists():
        PricingPlan.objects.create(
            setup_fee_etb=Decimal("15000"),
            quarterly_fee_etb=Decimal("5000"),
            description="Standard trainer plan",
            is_active=True,
        )


def unseed_plan(apps, schema_editor):
    PricingPlan = apps.get_model("platform_billing", "PricingPlan")
    PricingPlan.objects.filter(description="Standard trainer plan").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("platform_billing", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_plan, unseed_plan),
    ]
