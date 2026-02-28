from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom user model. Extends AbstractUser so we have room to grow.
    Added billing_tier in Q3 2022 to support the new pricing model.
    """

    TIER_FREE = "free"
    TIER_PRO = "pro"
    TIER_ENTERPRISE = "enterprise"

    BILLING_TIER_CHOICES = [
        (TIER_FREE, "Free"),
        (TIER_PRO, "Pro"),
        (TIER_ENTERPRISE, "Enterprise"),
    ]

    email = models.EmailField(unique=True)
    billing_tier = models.CharField(
        max_length=20,
        choices=BILLING_TIER_CHOICES,
        default=TIER_FREE,
    )
    company_name = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        db_table = "users"

    def __str__(self):
        return self.email

    @property
    def is_enterprise(self):
        return self.billing_tier == self.TIER_ENTERPRISE
