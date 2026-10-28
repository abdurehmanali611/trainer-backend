from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.auth import IsTrainerRole

from .models import Notification, PushToken
from .serializers import NotificationSerializer


class NotificationListView(APIView):
    permission_classes = [IsTrainerRole]

    def get(self, request):
        qs = Notification.objects.filter(target="trainer", user_id=request.user.id)
        unread_only = request.query_params.get("unread") == "true"
        if unread_only:
            qs = qs.filter(read=False)
        rows = list(qs[:100])
        return Response(
            {
                "unread": Notification.objects.filter(
                    target="trainer", user_id=request.user.id, read=False
                ).count(),
                "results": NotificationSerializer(rows, many=True).data,
            }
        )


class NotificationReadView(APIView):
    permission_classes = [IsTrainerRole]

    def post(self, request, pk):
        updated = Notification.objects.filter(
            target="trainer", user_id=request.user.id, id=pk
        ).update(read=True)
        if request.data.get("all"):
            Notification.objects.filter(target="trainer", user_id=request.user.id).update(
                read=True
            )
        return Response({"updated": updated})


class DeviceRegisterView(APIView):
    permission_classes = [IsTrainerRole]

    def post(self, request):
        token = request.data.get("token", "")
        if not token:
            return Response({"detail": "token required"}, status=400)
        PushToken.objects.update_or_create(
            user_type="trainer",
            user_id=request.user.id,
            defaults={"token": token},
        )
        return Response({"detail": "registered"})
