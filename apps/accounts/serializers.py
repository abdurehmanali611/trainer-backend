from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.core.auth import issue_trainer_jwt

from .models import Trainer


class TrainerTokenSerializer(TokenObtainPairSerializer):
    """Username + password -> JWT with role=trainer."""

    def validate(self, attrs):
        data = super().validate(attrs)
        data.update(issue_trainer_jwt(self.user))
        data["user_type"] = "trainer"
        data["trainer"] = {
            "id": self.user.id,
            "username": self.user.username,
            "full_name": self.user.full_name,
            "email": self.user.email,
            "gym_name": self.user.gym_name,
        }
        return data


class TrainerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Trainer
        fields = [
            "id", "username", "email", "full_name", "phone", "gym_name", "avatar_url",
            "inactive_days_threshold", "telebirr_number", "bank_name",
            "bank_account_name", "bank_account_number", "cash_note", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, label="Confirm password")
    setup_channel = serializers.CharField(write_only=True)
    setup_transaction_ref = serializers.CharField(write_only=True)

    class Meta:
        model = Trainer
        fields = [
            "username", "email", "password", "password2",
            "full_name", "phone", "gym_name",
            "setup_channel", "setup_transaction_ref",
        ]

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password2"):
            raise serializers.ValidationError({"password2": "Passwords do not match."})
        if Trainer.objects.filter(username__iexact=attrs["username"]).exists():
            raise serializers.ValidationError({"username": "Username already taken."})
        if Trainer.objects.filter(email__iexact=attrs["email"]).exists():
            raise serializers.ValidationError({"email": "Email already registered."})
        if not attrs["setup_channel"].strip():
            raise serializers.ValidationError({"setup_channel": "Payment channel is required."})
        if not attrs["setup_transaction_ref"].strip():
            raise serializers.ValidationError(
                {"setup_transaction_ref": "Transaction number is required."}
            )
        return attrs

    def create(self, validated_data):
        from apps.platform_billing.services import create_setup_payment

        channel = validated_data.pop("setup_channel")
        transaction_ref = validated_data.pop("setup_transaction_ref")
        trainer = Trainer.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
            full_name=validated_data.get("full_name", ""),
            phone=validated_data.get("phone", ""),
            gym_name=validated_data.get("gym_name", ""),
        )
        create_setup_payment(trainer, channel, transaction_ref, source="self_signup")
        return trainer


class PasswordForgotSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetSerializer(serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
