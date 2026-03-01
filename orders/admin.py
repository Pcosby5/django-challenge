from django.contrib import admin

from .models import Order, OrderLineItem, PaymentAttempt, Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "sku",
        "unit_price",
        "inventory_count",
        "is_active",
        "created_at",
    )
    search_fields = ("name", "sku")
    list_filter = ("is_active", "created_at")


class OrderLineItemInline(admin.TabularInline):
    model = OrderLineItem
    extra = 0
    readonly_fields = ("product", "quantity", "unit_price_snapshot")
    can_delete = False


class PaymentAttemptInline(admin.TabularInline):
    model = PaymentAttempt
    extra = 0
    readonly_fields = ("attempted_at", "result", "amount_charged", "provider_response")
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "customer",
        "status",
        "total_amount",
        "currency",
        "tax_amount",
        "external_payment_id",
        "created_at",
    )
    search_fields = ("id", "customer__email", "external_payment_id")
    list_filter = ("status", "currency", "created_at")
    readonly_fields = ("created_at", "updated_at", "paid_at")
    inlines = (OrderLineItemInline, PaymentAttemptInline)


@admin.register(PaymentAttempt)
class PaymentAttemptAdmin(admin.ModelAdmin):
    list_display = ("order", "result", "amount_charged", "attempted_at")
    search_fields = ("order__id", "order__customer__email")
    list_filter = ("result", "attempted_at")


@admin.register(OrderLineItem)
class OrderLineItemAdmin(admin.ModelAdmin):
    list_display = ("order", "product", "quantity", "unit_price_snapshot")
    search_fields = ("order__id", "product__sku", "product__name")
