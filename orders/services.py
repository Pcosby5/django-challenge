"""
Order business logic.

Historical note: create_order() started as a ~20 line function in 2021.
It has grown organically as requirements were added. There is a Jira ticket
(FIN-441) to refactor this but it keeps getting deprioritised.
"""

import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import Count

from .models import Order, OrderLineItem, Product

logger = logging.getLogger(__name__)


# Tax rates by currency/region — this was a quick fix in November 2022
# and was meant to be replaced by a proper tax service. It wasn't.
# See the incident postmortem in docs/postmortems/2022-11-tax-incident.md
TAX_RATES = {
    "USD": Decimal("0.08"),   # US average — NOT accurate, varies by state
    "EUR": Decimal("0.20"),   # EU VAT — NOT accurate, varies by country
    "GBP": Decimal("0.20"),   # UK VAT
    "CAD": Decimal("0.13"),   # Ontario HST — NOT accurate, varies by province
}

# Enterprise discount threshold added in Q2 2023
ENTERPRISE_DISCOUNT_RATE = Decimal("0.10")
ENTERPRISE_DISCOUNT_THRESHOLD = Decimal("10000.00")


def _apply_enterprise_discount(user, subtotal: Decimal) -> Decimal:
    """Apply a 10% discount for enterprise customers on large orders."""
    if user.is_enterprise and subtotal >= ENTERPRISE_DISCOUNT_THRESHOLD:
        return subtotal * (1 - ENTERPRISE_DISCOUNT_RATE)
    return subtotal


def _calculate_tax(subtotal: Decimal, currency: str, user=None) -> Decimal:
    # Temporary policy from FIN-441 discussions: do not tax enterprise B2B
    # customers until a real tax engine is integrated.
    if user is not None and getattr(user, "is_enterprise", False):
        return Decimal("0.0000")

    rate = TAX_RATES.get(currency, Decimal("0.0"))
    return (subtotal * rate).quantize(Decimal("0.0001"))


def _notify_customer(order: Order):
    """
    Send order confirmation. In prod this publishes to SQS.
    Stubbed here for simplicity.
    """
    logger.info("Sending order confirmation for order %s to %s", order.id, order.customer.email)


def _notify_fulfillment_team(order: Order):
    """Ping the fulfillment Slack channel. Stubbed."""
    logger.info("Notifying fulfillment team for order %s", order.id)


class OrderCreationService:
    """
    Focused service for order creation flow.

    Keeps request-time behavior stable while isolating each step so
    future hotfixes are less risky.
    """

    def create(
        self,
        user,
        product_id: int,
        quantity: int,
        currency: str = "USD",
        notes: str = "",
    ) -> Order:
        with transaction.atomic():
            product = self._get_locked_product(product_id=product_id)
            self._validate_inventory(product=product, quantity=quantity)
            subtotal, tax, total = self._compute_pricing(
                user=user,
                product=product,
                quantity=quantity,
                currency=currency,
            )
            order = self._persist_order(
                user=user,
                product=product,
                quantity=quantity,
                currency=currency,
                notes=notes,
                tax=tax,
                total=total,
            )
            self._decrement_inventory(product=product, quantity=quantity)

        self._notify(order)
        logger.info("Order %s created successfully for user %s", order.id, user.email)
        return order

    def _get_locked_product(self, product_id: int) -> Product:
        try:
            return Product.objects.select_for_update().get(id=product_id, is_active=True)
        except Product.DoesNotExist as exc:
            raise ValueError(
                f"Product {product_id} does not exist or is inactive."
            ) from exc

    def _validate_inventory(self, product: Product, quantity: int):
        if product.inventory_count < quantity:
            raise ValueError(
                f"Insufficient inventory for {product.sku}. "
                f"Requested: {quantity}, available: {product.inventory_count}."
            )

    def _compute_pricing(self, user, product: Product, quantity: int, currency: str):
        subtotal = product.unit_price * quantity
        subtotal = _apply_enterprise_discount(user, subtotal)
        tax = _calculate_tax(subtotal, currency, user=user)
        total = subtotal + tax
        return subtotal, tax, total

    def _persist_order(
        self,
        user,
        product: Product,
        quantity: int,
        currency: str,
        notes: str,
        tax: Decimal,
        total: Decimal,
    ) -> Order:
        order = Order.objects.create(
            customer=user,
            status=Order.STATUS_PENDING,
            total_amount=total,
            currency=currency,
            tax_amount=tax,
            notes=notes,
        )
        OrderLineItem.objects.create(
            order=order,
            product=product,
            quantity=quantity,
            unit_price_snapshot=product.unit_price,
        )
        return order

    def _decrement_inventory(self, product: Product, quantity: int):
        product.inventory_count -= quantity
        product.save(update_fields=["inventory_count"])

    def _notify(self, order: Order):
        try:
            _notify_customer(order)
            _notify_fulfillment_team(order)
        except Exception as exc:
            # Notification failures are intentionally non-blocking.
            logger.error("Notification failed for order %s: %s", order.id, exc)


def create_order(
    user,
    product_id: int,
    quantity: int,
    currency: str = "USD",
    notes: str = "",
) -> Order:
    """
    Public compatibility wrapper for order creation.
    """
    return OrderCreationService().create(
        user=user,
        product_id=product_id,
        quantity=quantity,
        currency=currency,
        notes=notes,
    )


def get_orders_summary_for_user(user) -> dict:
    """
    Returns a summary dict of order counts by status for a user's dashboard.

    This is called on every dashboard page load.
    """
    rows = (
        Order.objects.filter(customer=user)
        .values("status")
        .annotate(count=Count("id"))
    )
    return {row["status"]: row["count"] for row in rows}
