from datetime import date, datetime, time, timedelta

from django.db.models import Max, Sum
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.auth import IsTrainerRole

from .models import Client, Invoice, Payment, Session
from .serializers import ClientListSerializer
from .services import client_access_state


class DashboardView(APIView):
    permission_classes = [IsTrainerRole]

    def get(self, request):
        trainer = request.user
        clients = list(Client.objects.filter(trainer=trainer, is_active=True))
        today = date.today()
        month_start = today.replace(day=1)

        paid = trial = illustrative = due = blocked = needs_period = 0
        inactive_ids = []
        threshold = trainer.inactive_days_threshold or 7
        # Last completed session per client, fetched once instead of per row.
        last_completed = {
            row["client_id"]: row["last"]
            for row in Session.objects.filter(client__in=clients, status="completed")
            .values("client_id")
            .annotate(last=Max("date"))
        }
        for c in clients:
            if c.mode == "illustrative":
                illustrative += 1
            elif c.mode == "trial":
                trial += 1
            else:
                paid += 1
            access = client_access_state(c)
            if access["state"] == "blocked_no_period":
                # Brand new client who has not been given a period yet — that is
                # an onboarding step, not a blocked account.
                needs_period += 1
            elif access["state"] != "allowed":
                blocked += 1
            if access["state"] == "allowed" and access.get("reason") == "pay_window":
                due += 1
            # A client is inactive only once their inactivity *surpasses* the
            # trainer's limit. Measure from the last completed session, or from
            # the day they joined if they never had one, so brand-new clients
            # aren't flagged before they reach the limit.
            reference = last_completed.get(c.id) or c.created_at.date()
            if (today - reference).days > threshold:
                inactive_ids.append(c.id)

        inactive_clients = [c for c in clients if c.id in inactive_ids]

        invoices = Invoice.objects.filter(client__trainer=trainer)
        revenue_paid = (
            Payment.objects.filter(client__trainer=trainer, status="approved")
            .filter(decided_at__date__gte=month_start)
            .aggregate(total=Sum("invoice__amount"))["total"]
            or 0
        )
        revenue_by_channel = (
            Payment.objects.filter(client__trainer=trainer, status="approved")
            .filter(decided_at__date__gte=month_start)
            .values("channel")
            .annotate(total=Sum("invoice__amount"))
            .order_by("channel")
        )
        unpaid_count = invoices.filter(status__in=("pending", "overdue")).count()

        todays_sessions = Session.objects.filter(
            trainer=trainer, date=today
        ).select_related("client")

        retention = self._retention_rate(trainer, clients, today)

        return Response(
            {
                "counts": {
                    "total": len(clients),
                    "paid": paid,
                    "trial": trial,
                    "illustrative": illustrative,
                    "payment_due": due,
                    "blocked": blocked,
                    "needs_period": needs_period,
                    "inactive": len(inactive_clients),
                },
                "revenue_this_month": float(revenue_paid),
                "revenue_by_channel": [
                    {"channel": row["channel"], "total": float(row["total"] or 0)}
                    for row in revenue_by_channel
                ],
                "unpaid_invoices": unpaid_count,
                "retention_rate": retention,
                "inactive_threshold_days": threshold,
                "inactive_clients": ClientListSerializer(inactive_clients[:10], many=True).data,
                "today_sessions": [
                    {
                        "id": s.id,
                        "client_id": s.client_id,
                        "client_name": s.client.name,
                        "time": s.time.isoformat(),
                        "duration_minutes": s.duration_minutes,
                        "status": s.status,
                        "is_online": s.is_online,
                    }
                    for s in todays_sessions
                ],
            }
        )

    def _retention_rate(self, trainer, clients, today):
        """% of clients active at the start of the last 90 days who are still active."""
        window_start = today - timedelta(days=90)
        started = [c for c in clients if c.created_at.date() <= window_start]
        if not started:
            return {"value": None, "window_days": 90, "started": 0, "lost": 0}
        lost = [
            c
            for c in started
            if client_access_state(c)["state"] != "allowed"
        ]
        value = round((len(started) - len(lost)) / len(started) * 100, 1)
        return {
            "value": value,
            "window_days": 90,
            "started": len(started),
            "lost": len(lost),
        }


class WorkloadView(APIView):
    permission_classes = [IsTrainerRole]

    def get(self, request):
        trainer = request.user
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        days = []
        total_sessions = 0
        total_minutes = 0
        for i in range(7):
            day = monday + timedelta(days=i)
            sessions = Session.objects.filter(
                trainer=trainer, date=day
            ).exclude(status="canceled")
            count = sessions.count()
            minutes = sum(s.duration_minutes for s in sessions)
            total_sessions += count
            total_minutes += minutes
            days.append(
                {
                    "date": day.isoformat(),
                    "label": day.strftime("%a"),
                    "sessions": count,
                    "hours": round(minutes / 60, 1),
                    "is_today": day == today,
                }
            )
        client_count = Client.objects.filter(trainer=trainer, is_active=True).count()
        return Response(
            {
                "week_start": monday.isoformat(),
                "days": days,
                "totals": {
                    "sessions": total_sessions,
                    "hours": round(total_minutes / 60, 1),
                    "clients": client_count,
                    "avg_sessions_per_day": round(total_sessions / 7, 1),
                },
            }
        )
