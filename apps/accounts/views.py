from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.core.auth import IsTrainerRole, issue_trainer_jwt
from apps.core.utils import make_reset_token, read_reset_token, send_reset_email
from apps.platform_billing.services import (
    billing_payload,
    billing_state,
    ensure_billing,
    is_allowed,
)

from .serializers import (
    PasswordForgotSerializer,
    PasswordResetSerializer,
    RegisterSerializer,
    TrainerSerializer,
    TrainerTokenSerializer,
)

Trainer = get_user_model()


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        trainer = serializer.save()
        tokens = issue_trainer_jwt(trainer)
        billing = ensure_billing(trainer)
        return Response(
            {
                "trainer": TrainerSerializer(trainer).data,
                **tokens,
                "platform": billing_payload(billing),
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = TrainerTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        trainer = serializer.user
        if trainer.is_superuser:
            return Response(
                {"detail": "This admin account can't sign in to the trainer app. Use the admin console instead."},
                status=status.HTTP_403_FORBIDDEN,
            )
        billing = ensure_billing(trainer)
        payload = billing_payload(billing)
        if not trainer.is_active or not is_allowed(billing):
            return Response(
                {
                    "blocked": True,
                    "reason": billing_state(billing),
                    "billing": payload,
                },
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response({**serializer.validated_data, "platform": payload})


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = TrainerSerializer
    permission_classes = [IsTrainerRole]

    def get_object(self):
        return self.request.user


class PasswordForgotView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordForgotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        trainer = Trainer.objects.filter(email__iexact=email).first()
        if trainer:
            token = make_reset_token(trainer.id, "trainer")
            reset_url = f"{settings.TRAINER_APP_RESET_URL}?token={token}"
            send_reset_email(trainer.email, trainer.full_name or trainer.username, reset_url)
        return Response({"detail": "If that email exists, a reset link was sent."})


class PasswordResetView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        parsed = read_reset_token(serializer.validated_data["token"])
        if not parsed or parsed[0] != "trainer":
            return Response(
                {"detail": "Invalid or expired reset link."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        trainer = Trainer.objects.filter(id=parsed[1]).first()
        if not trainer:
            return Response(
                {"detail": "Invalid or expired reset link."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        trainer.set_password(serializer.validated_data["new_password"])
        trainer.save(update_fields=["password"])
        return Response({"detail": "Password updated. You can now log in."})


class LogoutView(APIView):
    """Expire the presented refresh **and** access tokens (sign out)."""

    def post(self, request):
        from rest_framework_simplejwt.exceptions import TokenError
        from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

        revoked = 0
        raw_refresh = request.data.get("refresh")
        if raw_refresh:
            try:
                RefreshToken(str(raw_refresh)).blacklist()
                revoked += 1
            except TokenError:
                pass

        if request.auth is not None:
            try:
                request.auth.blacklist()
                revoked += 1
            except TokenError:
                pass
        else:
            header = request.headers.get("Authorization", "")
            if header.startswith("Bearer "):
                try:
                    AccessToken(header[7:]).blacklist()
                    revoked += 1
                except TokenError:
                    pass

        return Response({"detail": "Session expired.", "revoked": revoked})
