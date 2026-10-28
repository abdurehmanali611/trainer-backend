from datetime import date

from django.db.models import Max
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.auth import IsTrainerRole

from .models import (
    Achievement,
    Client,
    FoodDiaryEntry,
    Measurement,
    PersonalRecord,
    ProgressPhoto,
    Session,
    SetLog,
    WaterLog,
)
from .serializers import (
    ClientCreateSerializer,
    ClientDetailSerializer,
    ClientListSerializer,
    FoodDiaryEntrySerializer,
    MeasurementSerializer,
    PersonalRecordSerializer,
    ProgressPhotoSerializer,
    WaterLogSerializer,
)
from .services import assert_within_trainer, client_access_state, notify_client


def trainer_clients_queryset(request):
    return Client.objects.filter(trainer=request.user, is_active=True)


class ClientListView(generics.ListCreateAPIView):
    permission_classes = [IsTrainerRole]
    search_fields = ("name", "phone", "email")

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ClientCreateSerializer
        return ClientListSerializer

    def get_queryset(self):
        qs = trainer_clients_queryset(self.request)
        mode = self.request.query_params.get("mode")
        if mode:
            qs = qs.filter(mode=mode)
        access = self.request.query_params.get("access")
        if access == "blocked":
            ids = [c.id for c in qs if client_access_state(c)["state"] != "allowed"]
            qs = qs.filter(id__in=ids)
        elif access == "inactive":
            threshold = self.request.user.inactive_days_threshold or 7
            today = date.today()
            # Same rule as the dashboard card: inactivity must *surpass* the
            # trainer's limit, counted from the last completed session (or the
            # day the client joined if they never had one).
            last_completed = {
                row["client_id"]: row["last"]
                for row in Session.objects.filter(client__in=qs, status="completed")
                .values("client_id")
                .annotate(last=Max("date"))
            }
            ids = [
                c.id
                for c in qs
                if (today - (last_completed.get(c.id) or c.created_at.date())).days > threshold
            ]
            qs = qs.filter(id__in=ids)
        search = self.request.query_params.get("search")
        if search:
            from django.db.models import Q

            qs = qs.filter(
                Q(name__icontains=search)
                | Q(phone__icontains=search)
                | Q(email__icontains=search)
            )
        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        serializer = ClientListSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = ClientCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        client = serializer.save()
        notify_client(
            client,
            "Welcome!",
            "Your trainer set up your account. Log in with the OTP they shared.",
        )
        return Response(ClientDetailSerializer(client).data, status=status.HTTP_201_CREATED)


class ClientDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsTrainerRole]
    serializer_class = ClientDetailSerializer

    def get_queryset(self):
        return trainer_clients_queryset(self.request)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active"])


class ClientOtpView(APIView):
    permission_classes = [IsTrainerRole]

    def post(self, request, pk):
        client = generics.get_object_or_404(trainer_clients_queryset(request), pk=pk)
        from .models import generate_unique_otp

        client.otp = generate_unique_otp()
        client.credential = ""
        client.must_change_credential = True
        client.save(update_fields=["otp", "credential", "must_change_credential"])
        return Response({"otp": client.otp})


class ClientModeView(APIView):
    permission_classes = [IsTrainerRole]

    def post(self, request, pk):
        client = generics.get_object_or_404(trainer_clients_queryset(request), pk=pk)
        mode = request.data.get("mode")
        if mode not in ("paid", "trial", "illustrative"):
            return Response({"detail": "Invalid mode."}, status=400)
        client.mode = mode
        client.save(update_fields=["mode"])
        return Response(ClientDetailSerializer(client).data)


class MeasurementListView(generics.ListCreateAPIView):
    permission_classes = [IsTrainerRole]
    serializer_class = MeasurementSerializer

    def get_queryset(self):
        return Measurement.objects.filter(
            client__trainer=self.request.user, client_id=self.kwargs["pk"]
        )

    def perform_create(self, serializer):
        client = generics.get_object_or_404(
            trainer_clients_queryset(self.request), pk=self.kwargs["pk"]
        )
        serializer.save(client=client)
        m = serializer.instance
        if m.weight is not None:
            client.current_weight = m.weight
        if m.body_fat is not None:
            client.body_fat = m.body_fat
        client.save(update_fields=["current_weight", "body_fat"])


class ProgressPhotoListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsTrainerRole]
    serializer_class = ProgressPhotoSerializer

    def get_queryset(self):
        return ProgressPhoto.objects.filter(
            client__trainer=self.request.user, client_id=self.kwargs["pk"]
        )

    def perform_create(self, serializer):
        client = generics.get_object_or_404(
            trainer_clients_queryset(self.request), pk=self.kwargs["pk"]
        )
        photo = serializer.save(client=client)
        ach, created = Achievement.objects.get_or_create(client=client, key="first_photo")
        if created:
            notify_client(client, "Achievement unlocked!", "First progress photo 📸", "achievement")


class ProgressPhotoDeleteView(generics.DestroyAPIView):
    permission_classes = [IsTrainerRole]
    serializer_class = ProgressPhotoSerializer
    queryset = ProgressPhoto.objects.all()


class PersonalRecordListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsTrainerRole]
    serializer_class = PersonalRecordSerializer

    def get_queryset(self):
        return PersonalRecord.objects.filter(
            client__trainer=self.request.user, client_id=self.kwargs["pk"]
        )

    def perform_create(self, serializer):
        client = generics.get_object_or_404(
            trainer_clients_queryset(self.request), pk=self.kwargs["pk"]
        )
        PersonalRecord.objects.filter(
            client=client, exercise__iexact=serializer.validated_data["exercise"]
        ).delete()
        serializer.save(client=client)


class FoodDiaryReviewView(generics.ListAPIView):
    permission_classes = [IsTrainerRole]
    serializer_class = FoodDiaryEntrySerializer

    def get_queryset(self):
        qs = FoodDiaryEntry.objects.filter(
            client__trainer=self.request.user, client_id=self.kwargs["pk"]
        )
        day = self.request.query_params.get("date")
        if day:
            qs = qs.filter(date=day)
        return qs


class FoodDiaryFeedbackView(APIView):
    permission_classes = [IsTrainerRole]

    def post(self, request, pk, entry_id):
        entry = generics.get_object_or_404(
            FoodDiaryEntry, id=entry_id, client__trainer=request.user, client_id=pk
        )
        entry.trainer_feedback = request.data.get("feedback", "")
        entry.status = "reviewed"
        entry.save(update_fields=["trainer_feedback", "status"])
        notify_client(
            entry.client,
            "Meal reviewed",
            entry.trainer_feedback or "Your trainer reviewed your food diary.",
            "alert",
        )
        return Response(FoodDiaryEntrySerializer(entry).data)


class WaterLogReviewView(APIView):
    permission_classes = [IsTrainerRole]

    def get(self, request, pk):
        qs = WaterLog.objects.filter(client__trainer=request.user, client_id=pk)
        day = request.query_params.get("date")
        if day:
            qs = qs.filter(date=day)
        return Response(WaterLogSerializer(qs, many=True).data)

    def post(self, request, pk, log_id=None):
        if log_id:
            log = generics.get_object_or_404(
                WaterLog, id=log_id, client__trainer=request.user, client_id=pk
            )
            log.trainer_feedback = request.data.get("feedback", "")
            log.reviewed = True
            log.save(update_fields=["trainer_feedback", "reviewed"])
            return Response(WaterLogSerializer(log).data)
        return Response({"detail": "log_id required"}, status=400)


class ClientAttendanceView(APIView):
    permission_classes = [IsTrainerRole]

    def get(self, request, pk):
        from .models import PermissionRequest, Session

        sessions = Session.objects.filter(client_id=pk, trainer=request.user)
        status_filter = request.query_params.get("status")
        if status_filter:
            sessions = sessions.filter(status=status_filter)
        rows = [
            {
                "id": s.id,
                "date": s.date.isoformat(),
                "time": s.time.isoformat(),
                "status": s.status,
                "duration_minutes": s.duration_minutes,
            }
            for s in sessions[:200]
        ]
        permissions = PermissionRequest.objects.filter(client_id=pk, trainer=request.user)
        return Response(
            {
                "sessions": rows,
                "permissions": [
                    {
                        "id": p.id,
                        "date": p.date.isoformat(),
                        "kind": p.kind,
                        "status": p.status,
                        "reason": p.reason,
                    }
                    for p in permissions[:100]
                ],
            }
        )


class ClientWorkoutProgressView(APIView):
    permission_classes = [IsTrainerRole]

    def get(self, request, pk):
        day = request.query_params.get("date")
        qs = SetLog.objects.filter(client_id=pk, client__trainer=request.user)
        if day:
            qs = qs.filter(date=day)
        logs = list(qs.order_by("date")[:500])
        by_day: dict[str, int] = {}
        for log in logs:
            key = log.date.isoformat()
            by_day[key] = by_day.get(key, 0) + (1 if log.completed else 0)
        return Response(
            {
                "by_day": [{"date": k, "sets": v} for k, v in sorted(by_day.items())],
                "logs": [
                    {
                        "date": log.date.isoformat(),
                        "exercise": log.exercise_name,
                        "set_index": log.set_index,
                        "weight": log.weight,
                        "reps": log.reps,
                        "completed": log.completed,
                    }
                    for log in logs[:100]
                ],
            }
        )
