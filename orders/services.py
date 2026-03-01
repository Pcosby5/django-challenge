"""
Order business logic.

Historical note: create_order() started as a ~20 line function in 2021.
It has grown organically as requirements were added. There is a Jira ticket
(FIN-441) to refactor this but it keeps getting deprioritised.
"""

import logging
from decimal import Decimal

from django.db import transaction

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


def _calculate_tax(subtotal: Decimal, currency: str) -> Decimal:
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


def create_order(user, product_id: int, quantity: int, currency: str = "USD", notes: str = "") -> Order:
    """
    Create a new order for a user.

    This function handles: product lookup, inventory check, pricing,
    discount application, tax calculation, line item creation, order
    persistence, and downstream notifications.

    It has grown too large. FIN-441 tracks the refactor.
    """
    with transaction.atomic():
        # --- 1. Fetch and validate the product (locked for consistency) ---
        try:
            product = Product.objects.select_for_update().get(id=product_id, is_active=True)
        except Product.DoesNotExist:
            raise ValueError(f"Product {product_id} does not exist or is inactive.")

        if product.inventory_count < quantity:
            raise ValueError(
                f"Insufficient inventory for {product.sku}. "
                f"Requested: {quantity}, available: {product.inventory_count}."
            )

        # --- 2. Calculate pricing ---
        subtotal = product.unit_price * quantity
        subtotal = _apply_enterprise_discount(user, subtotal)
        tax = _calculate_tax(subtotal, currency)
        total = subtotal + tax

        # --- 3. Create order and line item atomically ---
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

        # --- 4. Decrement inventory while still in the same transaction ---
        product.inventory_count -= quantity
        product.save(update_fields=["inventory_count"])

    # --- 5. Notify ---
    try:
        _notify_customer(order)
        _notify_fulfillment_team(order)
    except Exception as exc:
        # Swallowing notification errors intentionally — we don't want a
        # Slack/SQS blip to roll back a successful order.
        logger.error("Notification failed for order %s: %s", order.id, exc)

    logger.info("Order %s created successfully for user %s", order.id, user.email)
    return order


def get_orders_summary_for_user(user) -> dict:
    """
    Returns a summary dict of order counts by status for a user's dashboard.

    This is called on every dashboard page load.
    """
    orders = Order.objects.filter(customer=user)

    # BUG (performance / hidden): This loads ALL order objects into memory
    # just to count them by status. For a user with thousands of orders this
    # is very slow. Should use .values('status').annotate(count=Count('id')).
    summary = {}
    for order in orders:
        summary[order.status] = summary.get(order.status, 0) + 1

    return summary
