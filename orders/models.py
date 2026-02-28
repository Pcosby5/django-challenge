from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid


class Product(models.Model):
    """A product that can be ordered."""

    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=100, unique=True)
    # BUG (hidden): unit_price has more precision in the DB than the
    # serializer allows — values over $999,999.99 will be silently
    # truncated by the API layer. The DB column is fine; the serializer isn't.
    unit_price = models.DecimalField(max_digits=14, decimal_places=4)
    inventory_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "products"

    def __str__(self):
        return f"{self.name} ({self.sku})"


class Order(models.Model):
    """
    Core order record. Status lifecycle:
        pending → processing → paid → fulfilled → refunded
                             ↘ failed
    """

    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_PAID = "paid"
    STATUS_FULFILLED = "fulfilled"
    STATUS_FAILED = "failed"
    STATUS_REFUNDED = "refunded"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_PAID, "Paid"),
        (STATUS_FULFILLED, "Fulfilled"),
        (STATUS_FAILED, "Failed"),
        (STATUS_REFUNDED, "Refunded"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="orders",
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    # Total is stored separately (denormalised) for reporting performance.
    # It is calculated at order creation and must match sum(line_items).
    total_amount = models.DecimalField(max_digits=14, decimal_places=4)
    currency = models.CharField(max_length=3, default="USD")
    tax_amount = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    notes = models.TextField(blank=True)
    external_payment_id = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "orders"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"Order {self.id} ({self.status})"

    def get_line_total(self):
        return sum(item.line_total for item in self.line_items.all())


class OrderLineItem(models.Model):
    """A single product line within an order."""

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="line_items"
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="order_lines"
    )
    quantity = models.PositiveIntegerField()
    unit_price_snapshot = models.DecimalField(max_digits=14, decimal_places=4)

    class Meta:
        db_table = "order_line_items"

    @property
    def line_total(self):
        return self.quantity * self.unit_price_snapshot

    def __str__(self):
        return f"{self.quantity}x {self.product.name}"


class PaymentAttempt(models.Model):
    """Audit log of every payment attempt against an order."""

    RESULT_SUCCESS = "success"
    RESULT_FAILURE = "failure"
    RESULT_PENDING = "pending"

    RESULT_CHOICES = [
        (RESULT_SUCCESS, "Success"),
        (RESULT_FAILURE, "Failure"),
        (RESULT_PENDING, "Pending"),
    ]

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="payment_attempts"
    )
    attempted_at = models.DateTimeField(default=timezone.now)
    result = models.CharField(
        max_length=20, choices=RESULT_CHOICES, default=RESULT_PENDING
    )
    provider_response = models.JSONField(default=dict)
    amount_charged = models.DecimalField(max_digits=14, decimal_places=4)

    class Meta:
        db_table = "payment_attempts"
        ordering = ["-attempted_at"]
