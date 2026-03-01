from rest_framework import serializers
from .models import Order, OrderLineItem, Product


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ["id", "name", "sku", "unit_price", "inventory_count"]


class OrderLineItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = OrderLineItem
        fields = [
            "id",
            "product",
            "product_name",
            "product_sku",
            "quantity",
            "unit_price_snapshot",
            "line_total",
        ]

    def get_line_total(self, obj):
        return obj.line_total


class OrderSerializer(serializers.ModelSerializer):
    line_items = OrderLineItemSerializer(many=True, read_only=True)
    customer_email = serializers.EmailField(source="customer.email", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "customer_email",
            "status",
            "total_amount",
            "currency",
            "tax_amount",
            "notes",
            "external_payment_id",
            "created_at",
            "updated_at",
            "paid_at",
            "line_items",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "paid_at",
            "external_payment_id",
        ]


class CreateOrderSerializer(serializers.Serializer):
    """Serializer for the order creation endpoint."""

    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)
    currency = serializers.CharField(max_length=3, default="USD")
    notes = serializers.CharField(required=False, allow_blank=True)
