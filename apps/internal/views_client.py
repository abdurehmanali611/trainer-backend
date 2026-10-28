"""Client-scoped endpoints served to the trainer-client gateway."""
from datetime import date, datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.fitness.models import (
    Achievement,
    Client,
    DietPlan,
    Exercise,
    FoodDiaryEntry,
    Invoice,
    Measurement,
    Message,
    Notification,
    Payment,
    PersonalRecord,
    ProgressPhoto,
    PermissionRequest,
    PushToken,
    RescheduleRequest,
    Session,
    SetLog,
    Streak,
    WaterLog,
    WorkoutPlan,
)
from apps.fitness.serializers import (
    AchievementSerializer,
    DietPlanSerializer,
    ExerciseSerializer,
    FoodDiaryEntrySerializer,
    MeasurementSerializer,
    MessageSerializer,
    NotificationSerializer,
    PersonalRecordSerializer,
    ProgressPhotoSerializer,
    PermissionRequestSerializer,
    RescheduleRequestSerializer,
    StreakSerializer,
    WaterLogSerializer,
    WorkoutPlanSerializer,
)
from apps.fitness.services import (
    client_access_state,
    client_payment_payload,
    notify_trainer,
)

from .views_auth import ServiceTokenPermission, require_client


class ClientAPIView(APIView):
    authentication_classes = []
    permission_classes = [ServiceTokenPermission]

    def client(self, request) -> Client:
        return require_client(request)


class MeView(ClientAPIView):
    def get(self, request):
        c = self.client(request)
        access = client_access_state(c)
        return Response(
            {
                "id": c.id,
                "name": c.name,
                "phone": c.phone,
                "email": c.email,
                "mode": c.mode,
                "avatar_url": c.avatar_url,
                "goals": c.goals,
                "medical_history": c.medical_history,
                "emergency_contact": c.emergency_contact,
                "current_weight": c.current_weight,
                "target_weight": c.target_weight,
                "body_fat": c.body_fat,
                "created_at": c.created_at.isoformat(),
                "trainer_name": c.trainer.full_name or c.trainer.username,
                "access": access,
                "streak": StreakSerializer(
                    Streak.objects.filter(client=c).first(), many=False
                ).data
                if Streak.objects.filter(client=c).exists()
                else {"current": 0, "longest": 0},
            }
        )


class TodayView(ClientAPIView):
    """Home screen payload: today's workout, meals, next session, billing."""

    def get(self, request):
        c = self.client(request)
        today = date.today()
        weekday = today.strftime("%A")

        plan = (
            c.workout_plans.order_by("-updated_at").select_related("client").first()
        )
        today_workout = None
        other_days = []
        if plan:
            days = list(plan.days.prefetch_related("exercises__exercise"))
            for day in days:
                payload = {
                    "id": day.id,
                    "day_name": day.day_name,
                    "order": day.order,
                    "is_today": day.day_name.lower().startswith(weekday[:3].lower())
                    or day.day_name.lower() == weekday.lower(),
                    "exercises": [
                        {
                            "id": pe.id,
                            "name": pe.exercise.name,
                            "sets": pe.sets,
                            "reps": pe.reps,
                            "target_weight": pe.target_weight,
                            "rest_seconds": pe.rest_seconds,
                            "video_url": pe.exercise.video_url,
                            "description": pe.exercise.description,
                            "muscle_group": pe.exercise.muscle_group,
                        }
                        for pe in day.exercises.all()
                    ],
                }
                if payload["is_today"] and today_workout is None:
                    today_workout = payload
                other_days.append(payload)
            if today_workout is None and other_days:
                today_workout = other_days[0]

        diet = c.diet_plans.order_by("-created_at").first()
        meals = []
        macros = None
        if diet:
            macros = {
                "daily_calories": diet.daily_calories,
                "protein": diet.protein,
                "carbs": diet.carbs,
                "fats": diet.fats,
                "name": diet.name,
            }
            for meal in diet.meals.all():
                meals.append(
                    {
                        "name": meal.name,
                        "time": meal.time,
                        "items": [
                            {
                                "name": item.name,
                                "calories": item.calories,
                                "protein": item.protein,
                                "carbs": item.carbs,
                                "fats": item.fats,
                            }
                            for item in meal.items.all()
                        ],
                    }
                )

        next_session = (
            Session.objects.filter(client=c, date__gte=today)
            .exclude(status="canceled")
            .order_by("date", "time")
            .first()
        )
        todays_sessions = Session.objects.filter(client=c, date=today)

        water = WaterLog.objects.filter(client=c, date=today).first()

        return Response(
            {
                "today_workout": today_workout,
                "other_days": other_days,
                "diet": {"macros": macros, "meals": meals},
                "next_session": (
                    {
                        "id": next_session.id,
                        "date": next_session.date.isoformat(),
                        "time": next_session.time.isoformat(),
                        "duration_minutes": next_session.duration_minutes,
                        "is_online": next_session.is_online,
                        "status": next_session.status,
                    }
                    if next_session
                    else None
                ),
                "today_sessions": [
                    {
                        "id": s.id,
                        "date": s.date.isoformat(),
                        "time": s.time.isoformat(),
                        "duration_minutes": s.duration_minutes,
                        "status": s.status,
                        "is_online": s.is_online,
                    }
                    for s in todays_sessions
                ],
                "water": WaterLogSerializer(water).data if water else None,
                "billing": client_payment_payload(c),
                "streak": StreakSerializer(
                    Streak.objects.filter(client=c).first()
                ).data
                if Streak.objects.filter(client=c).exists()
                else {"current": 0, "longest": 0},
            }
        )


class PlanListView(ClientAPIView):
    def get(self, request):
        c = self.client(request)
        plans = WorkoutPlan.objects.filter(client=c)
        return Response(WorkoutPlanSerializer(plans, many=True).data)


class PlanDetailView(ClientAPIView):
    def get(self, request, pk):
        c = self.client(request)
        plan = WorkoutPlan.objects.filter(client=c, pk=pk).first()
        if not plan:
            return Response({"detail": "Not found."}, status=404)
        return Response(WorkoutPlanSerializer(plan).data)


class DietView(ClientAPIView):
    def get(self, request):
        c = self.client(request)
        diet = DietPlan.objects.filter(client=c).order_by("-created_at").first()
        if not diet:
            return Response({"detail": "No diet plan assigned."}, status=404)
        return Response(DietPlanSerializer(diet).data)


class ExerciseLibraryView(ClientAPIView):
    def get(self, request):
        qs = Exercise.objects.filter(
            Q(trainer__isnull=True) | Q(trainer=self.client(request).trainer)
        )
        group = request.query_params.get("group")
        if group and group != "All":
            qs = qs.filter(muscle_group=group)
        search = request.query_params.get("search")
        if search:
            qs = qs.filter(name__icontains=search)
        return Response(ExerciseSerializer(qs.order_by("name")[:200], many=True).data)


class ScheduleView(ClientAPIView):
    def get(self, request):
        c = self.client(request)
        qs = Session.objects.filter(client=c)
        start = request.query_params.get("from")
        end = request.query_params.get("to")
        if start:
            qs = qs.filter(date__gte=start)
        if end:
            qs = qs.filter(date__lte=end)
        rows = [
            {
                "id": s.id,
                "date": s.date.isoformat(),
                "time": s.time.isoformat(),
                "duration_minutes": s.duration_minutes,
                "status": s.status,
                "is_online": s.is_online,
                "notes": s.notes,
                "is_today": s.date == date.today(),
            }
            for s in qs.order_by("date", "time")[:200]
        ]
        return Response(rows)


class RescheduleRequestCreateView(ClientAPIView):
    def post(self, request):
        c = self.client(request)
        session = Session.objects.filter(client=c, pk=request.data.get("session_id")).first()
        if not session:
            return Response({"detail": "Session not found."}, status=404)
        requested_date = request.data.get("requested_date")
        if not requested_date:
            return Response({"detail": "requested_date is required."}, status=400)
        req = RescheduleRequest.objects.create(
            session=session,
            client=c,
            requested_date=requested_date,
            requested_time=request.data.get("requested_time") or None,
            reason=request.data.get("reason", ""),
        )
        notify_trainer(
            c.trainer,
            "Reschedule request",
            f"{c.name} wants to move session {session.date.isoformat()} to {requested_date}.",
            "request",
            {"reschedule_request_id": req.id, "client_id": c.id},
        )
        return Response(
            RescheduleRequestSerializer(req).data, status=status.HTTP_201_CREATED
        )


class PermissionRequestCreateView(ClientAPIView):
    def post(self, request):
        c = self.client(request)
        kind = request.data.get("kind")
        day = request.data.get("date")
        if kind not in ("late", "absent") or not day:
            return Response({"detail": "kind (late|absent) and date required."}, status=400)
        session = Session.objects.filter(client=c, date=day).first()
        req = PermissionRequest.objects.create(
            client=c,
            session=session,
            date=day,
            kind=kind,
            reason=request.data.get("reason", ""),
        )
        notify_trainer(
            c.trainer,
            f"{req.get_kind_display()} request",
            f"{c.name} requests {kind} on {day}: {req.reason or 'no reason given'}",
            "request",
            {"permission_request_id": req.id, "client_id": c.id},
        )
        return Response(
            PermissionRequestSerializer(req).data, status=status.HTTP_201_CREATED
        )


class MyRequestsView(ClientAPIView):
    def get(self, request):
        c = self.client(request)
        reschedules = RescheduleRequest.objects.filter(client=c).order_by("-created_at")[:50]
        permissions = PermissionRequest.objects.filter(client=c).order_by("-created_at")[:50]
        return Response(
            {
                "reschedules": RescheduleRequestSerializer(reschedules, many=True).data,
                "permissions": PermissionRequestSerializer(permissions, many=True).data,
            }
        )


class MyAttendanceView(ClientAPIView):
    def get(self, request):
        c = self.client(request)
        sessions = Session.objects.filter(client=c).order_by("-date")[:200]
        summary = {"completed": 0, "no_show": 0, "canceled": 0, "scheduled": 0}
        rows = []
        for s in sessions:
            summary[s.status] = summary.get(s.status, 0) + 1
            rows.append(
                {
                    "id": s.id,
                    "date": s.date.isoformat(),
                    "time": s.time.isoformat(),
                    "status": s.status,
                }
            )
        return Response({"summary": summary, "sessions": rows})


class MyBillingView(ClientAPIView):
    def get(self, request):
        c = self.client(request)
        return Response(client_payment_payload(c))

    def post(self, request):
        """Submit payment: transaction id only (amount fixed by trainer)."""
        c = self.client(request)
        transaction_id = (request.data.get("transaction_id") or "").strip()
        channel = request.data.get("channel", "telebirr")
        if not transaction_id:
            return Response({"detail": "transaction_id is required."}, status=400)
        billing = client_payment_payload(c)
        invoice_id = request.data.get("invoice_id") or (billing.get("invoice") or {}).get("id")
        if not invoice_id:
            return Response(
                {"detail": "No pending invoice right now."}, status=400
            )
        invoice = Invoice.objects.filter(pk=invoice_id, client=c).first()
        if not invoice:
            return Response({"detail": "Invoice not found."}, status=404)
        payment = Payment.objects.create(
            invoice=invoice,
            client=c,
            transaction_id=transaction_id,
            channel=channel if channel in ("cash", "bank", "telebirr") else "telebirr",
        )
        notify_trainer(
            c.trainer,
            "Payment submitted",
            f"{c.name} submitted {payment.transaction_id} ({payment.channel}).",
            "payment",
            {"payment_id": payment.id, "client_id": c.id},
        )
        return Response(
            {
                "detail": "Payment submitted. Waiting for your trainer's approval.",
                "payment_id": payment.id,
            },
            status=status.HTTP_201_CREATED,
        )


class InvoiceListView(ClientAPIView):
    def get(self, request):
        c = self.client(request)
        from apps.fitness.serializers import InvoiceSerializer

        invoices = Invoice.objects.filter(client=c).prefetch_related("payments", "period")
        return Response(InvoiceSerializer(invoices, many=True).data)


class ChatMessagesView(ClientAPIView):
    def get(self, request):
        c = self.client(request)
        qs = c.messages.order_by("-created_at")
        before = request.query_params.get("before")
        if before:
            qs = qs.filter(created_at__lt=before)
        rows = list(qs[:100])
        rows.reverse()
        return Response(MessageSerializer(rows, many=True).data)

    def post(self, request):
        c = self.client(request)
        kind = request.data.get("kind", "text")
        content = request.data.get("content", "")
        media_urls = request.data.get("media_urls", []) or []
        if kind not in ("text", "image", "voice"):
            return Response({"detail": "Invalid kind."}, status=400)
        if not content and not media_urls:
            return Response({"detail": "Empty message."}, status=400)
        if kind == "image" and len(media_urls) > 5:
            return Response({"detail": "Max 5 images per message."}, status=400)
        msg = Message.objects.create(
            sender_type="client",
            client=c,
            content=content,
            kind=kind,
            media_urls=media_urls[:5],
            client_read_at=timezone.now(),
        )
        notify_trainer(
            c.trainer,
            f"Message from {c.name}",
            content[:120] or ("📷 Photo" if kind == "image" else "🎤 Voice note"),
            "message",
            {"client_id": c.id},
        )
        return Response(MessageSerializer(msg).data, status=status.HTTP_201_CREATED)


class ChatReadView(ClientAPIView):
    def post(self, request):
        c = self.client(request)
        updated = Message.objects.filter(
            client=c, sender_type="trainer", client_read_at__isnull=True
        ).update(client_read_at=timezone.now())
        return Response({"updated": updated})


class FoodDiaryView(ClientAPIView):
    def get(self, request):
        c = self.client(request)
        qs = FoodDiaryEntry.objects.filter(client=c)
        day = request.query_params.get("date")
        if day:
            qs = qs.filter(date=day)
        return Response(FoodDiaryEntrySerializer(qs[:100], many=True).data)

    def post(self, request):
        c = self.client(request)
        entry = FoodDiaryEntry.objects.create(
            client=c,
            date=request.data.get("date") or date.today().isoformat(),
            meal_name=request.data.get("meal_name", ""),
            description=request.data.get("description", ""),
            calories=request.data.get("calories") or None,
            photo_url=request.data.get("photo_url", ""),
        )
        return Response(
            FoodDiaryEntrySerializer(entry).data, status=status.HTTP_201_CREATED
        )


class WaterView(ClientAPIView):
    def get(self, request):
        c = self.client(request)
        qs = WaterLog.objects.filter(client=c)
        day = request.query_params.get("date")
        if day:
            qs = qs.filter(date=day)
        return Response(WaterLogSerializer(qs[:60], many=True).data)

    def post(self, request):
        c = self.client(request)
        day = request.data.get("date") or date.today().isoformat()
        amount = int(request.data.get("amount_ml") or 250)
        log, _ = WaterLog.objects.get_or_create(client=c, date=day)
        log.amount_ml += amount
        log.save(update_fields=["amount_ml"])
        return Response(WaterLogSerializer(log).data)


class MeasurementsView(ClientAPIView):
    def get(self, request):
        c = self.client(request)
        return Response(MeasurementSerializer(c.measurements.all()[:60], many=True).data)

    def post(self, request):
        c = self.client(request)
        day = request.data.get("date") or date.today().isoformat()
        serializer = MeasurementSerializer(data={**request.data, "date": day})
        serializer.is_valid(raise_exception=True)
        existing = Measurement.objects.filter(client=c, date=day).first()
        if existing:
            for attr, value in serializer.validated_data.items():
                setattr(existing, attr, value)
            existing.save()
            serializer.instance = existing
        else:
            serializer.save(client=c)
        m = serializer.instance
        if m.weight is not None:
            c.current_weight = m.weight
        if m.body_fat is not None:
            c.body_fat = m.body_fat
        c.save(update_fields=["current_weight", "body_fat"])
        ach, created = Achievement.objects.get_or_create(client=c, key="first_weight_log")
        return Response(MeasurementSerializer(m).data, status=201)


class PhotosView(ClientAPIView):
    def get(self, request):
        c = self.client(request)
        return Response(ProgressPhotoSerializer(c.photos.all()[:60], many=True).data)

    def post(self, request):
        c = self.client(request)
        url = request.data.get("url", "")
        if not url:
            return Response({"detail": "url required"}, status=400)
        photo = ProgressPhoto.objects.create(
            client=c,
            url=url,
            date=request.data.get("date") or date.today().isoformat(),
            note=request.data.get("note", ""),
        )
        Achievement.objects.get_or_create(client=c, key="first_photo")
        return Response(ProgressPhotoSerializer(photo).data, status=201)


class RecordsView(ClientAPIView):
    def get(self, request):
        c = self.client(request)
        return Response(PersonalRecordSerializer(c.records.all()[:50], many=True).data)


class WorkoutLogView(ClientAPIView):
    """Save set logs for today's workout."""

    def post(self, request):
        c = self.client(request)
        day = request.data.get("date") or date.today().isoformat()
        entries = request.data.get("entries") or []
        now = timezone.now()
        created = []
        for entry in entries:
            log = SetLog.objects.create(
                client=c,
                planned_exercise_id=entry.get("planned_exercise") or None,
                exercise_name=entry.get("exercise_name", ""),
                date=day,
                set_index=entry.get("set_index", 1),
                weight=entry.get("weight", 0),
                reps=entry.get("reps", 0),
                completed=bool(entry.get("completed", True)),
                completed_at=now if entry.get("completed", True) else None,
            )
            created.append(log.id)
        return Response({"logged": len(created)}, status=201)


class WorkoutCompleteView(ClientAPIView):
    """Mark the day's workout complete -> streak + achievements."""

    def post(self, request):
        c = self.client(request)
        day_str = request.data.get("date") or date.today().isoformat()
        day = datetime.strptime(day_str, "%Y-%m-%d").date()
        total_workouts = SetLog.objects.filter(client=c, completed=True).values("date").distinct().count()

        new_achievements = []
        streak, _ = Streak.objects.get_or_create(client=c)
        if not Streak.objects.filter(client=c).exists():
            streak.save()
        new_achievements += streak.register_activity(day)

        for key, needed in (
            ("first_workout", 1),
            ("ten_workouts", 10),
            ("fifty_workouts", 50),
        ):
            if total_workouts >= needed:
                ach, created = Achievement.objects.get_or_create(client=c, key=key)
                if created:
                    new_achievements.append(ach)

        for ach in new_achievements:
            notify_trainer(
                c.trainer,
                "Achievement unlocked",
                f"{c.name} unlocked: {ach.get_key_display()}",
                "achievement",
                {"client_id": c.id},
            )
        streak = Streak.objects.get(client=c)
        return Response(
            {
                "streak": StreakSerializer(streak).data,
                "new_achievements": AchievementSerializer(new_achievements, many=True).data,
                "total_workouts": total_workouts,
            }
        )


class AchievementsView(ClientAPIView):
    def get(self, request):
        c = self.client(request)
        streak, _ = Streak.objects.get_or_create(client=c)
        return Response(
            {
                "streak": StreakSerializer(streak).data,
                "achievements": AchievementSerializer(
                    c.achievements.all()[:50], many=True
                ).data,
                "all_keys": [{"key": k, "label": l} for k, l in Achievement.KEYS],
            }
        )


class NotificationListView(ClientAPIView):
    def get(self, request):
        c = self.client(request)
        qs = Notification.objects.filter(target="client", user_id=c.id)
        rows = list(qs[:100])
        return Response(
            {
                "unread": qs.filter(read=False).count(),
                "results": NotificationSerializer(rows, many=True).data,
            }
        )

    def post(self, request):
        c = self.client(request)
        if request.data.get("all"):
            Notification.objects.filter(target="client", user_id=c.id).update(read=True)
        elif request.data.get("id"):
            Notification.objects.filter(target="client", user_id=c.id, id=request.data["id"]).update(read=True)
        return Response({"detail": "ok"})


class DeviceRegisterView(ClientAPIView):
    def post(self, request):
        c = self.client(request)
        token = request.data.get("token", "")
        if token:
            PushToken.objects.update_or_create(
                user_type="client", user_id=c.id, defaults={"token": token}
            )
        return Response({"detail": "registered"})
