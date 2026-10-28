from datetime import date, datetime

from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.auth import IsTrainerRole

from .models import PermissionRequest, RescheduleRequest, Session
from .serializers import (
    PermissionRequestSerializer,
    RescheduleRequestSerializer,
    SessionSerializer,
)
from .services import notify_client, notify_trainer


class SessionListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsTrainerRole]
    serializer_class = SessionSerializer

    def get_queryset(self):
        qs = Session.objects.filter(trainer=self.request.user).select_related("client")
        day = self.request.query_params.get("date")
        if day:
            qs = qs.filter(date=day)
        start = self.request.query_params.get("from")
        end = self.request.query_params.get("to")
        if start:
            qs = qs.filter(date__gte=start)
        if end:
            qs = qs.filter(date__lte=end)
        client_id = self.request.query_params.get("client")
        if client_id:
            qs = qs.filter(client_id=client_id)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = serializer.save(trainer=request.user)
        notify_client(
            session.client,
            "Session scheduled",
            f"New session on {session.date.isoformat()} at {session.time.strftime('%H:%M')}",
            "booking",
            {"session_id": session.id},
        )
        return Response(SessionSerializer(session).data, status=status.HTTP_201_CREATED)


class SessionDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsTrainerRole]
    serializer_class = SessionSerializer

    def get_queryset(self):
        return Session.objects.filter(trainer=self.request.user)

    def perform_update(self, serializer):
        session = serializer.save()
        notify_client(
            session.client,
            "Session updated",
            f"Your session is now {session.date.isoformat()} at {session.time.strftime('%H:%M')} "
            f"({session.get_status_display()})",
            "booking",
            {"session_id": session.id},
        )


class RequestQueueView(APIView):
    """GET /api/requests/?type=reschedule|permission&status=pending"""

    permission_classes = [IsTrainerRole]

    def get(self, request):
        req_type = request.query_params.get("type", "reschedule")
        req_status = request.query_params.get("status", "pending")
        if req_type == "permission":
            qs = PermissionRequest.objects.filter(
                client__trainer=request.user, status=req_status
            ).select_related("client", "session")
            return Response(PermissionRequestSerializer(qs, many=True).data)
        qs = RescheduleRequest.objects.filter(
            client__trainer=request.user, status=req_status
        ).select_related("client", "session")
        return Response(RescheduleRequestSerializer(qs, many=True).data)


class RescheduleDecideView(APIView):
    permission_classes = [IsTrainerRole]

    def post(self, request, pk):
        req = generics.get_object_or_404(
            RescheduleRequest, pk=pk, client__trainer=request.user, status="pending"
        )
        approve = bool(request.data.get("approve"))
        note = request.data.get("note", "")
        req.status = "approved" if approve else "declined"
        req.trainer_note = note
        req.decided_at = timezone.now()
        req.save()
        if approve and req.session_id:
            session = req.session
            session.date = req.requested_date
            if req.requested_time:
                session.time = req.requested_time
            session.save(update_fields=["date", "time"])
            notify_client(
                req.client,
                "Reschedule approved",
                f"Your session moved to {session.date.isoformat()} "
                f"at {session.time.strftime('%H:%M')}",
                "booking",
                {"session_id": session.id},
            )
        else:
            notify_client(
                req.client,
                "Reschedule declined",
                note or "Your trainer declined the reschedule request.",
                "booking",
            )
        return Response(RescheduleRequestSerializer(req).data)


class PermissionDecideView(APIView):
    permission_classes = [IsTrainerRole]

    def post(self, request, pk):
        req = generics.get_object_or_404(
            PermissionRequest, pk=pk, client__trainer=request.user, status="pending"
        )
        approve = bool(request.data.get("approve"))
        note = request.data.get("note", "")
        req.status = "approved" if approve else "declined"
        req.trainer_note = note
        req.decided_at = timezone.now()
        req.save()
        if approve and req.session_id and req.kind == "absent":
            session = req.session
            session.status = "canceled"
            session.save(update_fields=["status"])
        notify_client(
            req.client,
            f"{req.get_kind_display()} request {'approved' if approve else 'declined'}",
            note or f"Your {req.get_kind_display().lower()} request was {'approved' if approve else 'declined'}.",
            "request",
        )
        return Response(PermissionRequestSerializer(req).data)


class AttendanceListView(APIView):
    """GET /api/attendance/?client=&from=&to= — all clients or one."""

    permission_classes = [IsTrainerRole]

    def get(self, request):
        qs = Session.objects.filter(trainer=request.user).select_related("client")
        client_id = request.query_params.get("client")
        if client_id:
            qs = qs.filter(client_id=client_id)
        start = request.query_params.get("from")
        end = request.query_params.get("to")
        if start:
            qs = qs.filter(date__gte=start)
        if end:
            qs = qs.filter(date__lte=end)
        rows = [
            {
                "id": s.id,
                "client_id": s.client_id,
                "client_name": s.client.name,
                "date": s.date.isoformat(),
                "time": s.time.isoformat(),
                "status": s.status,
            }
            for s in qs.order_by("-date")[:500]
        ]
        summary: dict[int, dict] = {}
        for s in qs:
            row = summary.setdefault(
                s.client_id,
                {"client_id": s.client_id, "client_name": s.client.name,
                 "completed": 0, "no_show": 0, "canceled": 0, "scheduled": 0},
            )
            row[s.status] = row.get(s.status, 0) + 1
        return Response({"sessions": rows, "summary": list(summary.values())})
