from rest_framework import serializers

from .models import User


class UserMeSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "username",
            "billing_tier",
            "company_name",
            "is_staff",
            "is_superuser",
        )
