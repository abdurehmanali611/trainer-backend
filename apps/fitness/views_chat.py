import uuid

from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.auth import IsTrainerRole

from .models import Client, Message
from .serializers import MessageSerializer, ThreadSerializer
from .services import notify_client


class ThreadListView(APIView):
    permission_classes = [IsTrainerRole]

    def get(self, request):
        clients = Client.objects.filter(trainer=request.user, is_active=True)
        data = ThreadSerializer(clients, many=True).data
        data = sorted(
            data,
            key=lambda row: (row.get("last_message") or {}).get("created_at") or "",
            reverse=True,
        )
        return Response(data)


class ThreadMessagesView(APIView):
    permission_classes = [IsTrainerRole]

    def get(self, request, client_id):
        client = Client.objects.get(id=client_id, trainer=request.user)
        qs = client.messages.order_by("-created_at")
        before = request.query_params.get("before")
        if before:
            qs = qs.filter(created_at__lt=before)
        limit = int(request.query_params.get("limit", 50))
        rows = list(qs[:limit])
        rows.reverse()
        return Response(MessageSerializer(rows, many=True).data)

    def post(self, request, client_id):
        client = Client.objects.get(id=client_id, trainer=request.user)
        kind = request.data.get("kind", "text")
        content = request.data.get("content", "")
        media_urls = request.data.get("media_urls", []) or []
        if kind == "text" and not content.strip():
            return Response({"detail": "Empty message."}, status=400)
        msg = Message.objects.create(
            sender_type="trainer",
            client=client,
            content=content,
            kind=kind,
            media_urls=media_urls[:5],
            trainer_read_at=timezone.now(),
        )
        notify_client(client, f"Message from {request.user.full_name or request.user.username}",
                      content or "Sent an attachment", "message")
        return Response(MessageSerializer(msg).data, status=status.HTTP_201_CREATED)


class ThreadReadView(APIView):
    permission_classes = [IsTrainerRole]

    def post(self, request, client_id):
        updated = Message.objects.filter(
            client_id=client_id, client__trainer=request.user,
            sender_type="client", trainer_read_at__isnull=True,
        ).update(trainer_read_at=timezone.now())
        return Response({"updated": updated})


class BroadcastView(APIView):
    """Send one message to many of my clients (checkbox selection)."""

    permission_classes = [IsTrainerRole]

    def post(self, request):
        client_ids = request.data.get("client_ids") or []
        if not client_ids or not all(str(i).isdigit() for i in client_ids):
            return Response({"detail": "client_ids required."}, status=400)
        content = request.data.get("content", "")
        kind = request.data.get("kind", "text")
        media_urls = request.data.get("media_urls", []) or []
        clients = Client.objects.filter(
            id__in=[int(i) for i in client_ids], trainer=request.user, is_active=True
        )
        broadcast_id = uuid.uuid4().hex
        created = []
        for client in clients:
            msg = Message.objects.create(
                sender_type="trainer",
                client=client,
                content=content,
                kind=kind,
                media_urls=media_urls[:5],
                is_broadcast=True,
                broadcast_id=broadcast_id,
                trainer_read_at=timezone.now(),
            )
            created.append(msg.id)
            notify_client(
                client,
                "Broadcast from your trainer",
                content or "Sent an attachment",
                "message",
                {"broadcast_id": broadcast_id},
            )
        return Response(
            {"broadcast_id": broadcast_id, "sent": len(created)},
            status=status.HTTP_201_CREATED,
        )
