"""
Celery tasks for async order processing.

These tasks are triggered by the payment webhook handler and by the
order creation flow. They run in a separate worker process.
"""

import logging

from celery import shared_task
from django.utils import timezone

from .models import Order, PaymentAttempt

logger = logging.getLogger(__name__)


def charge_payment_provider(order: Order) -> dict:
    """
    Stub for the real payment provider integration (Stripe in prod).
    Returns a fake provider response.
    In production this makes an HTTP call to Stripe's charges API.
    """
    logger.info("[STUB] Charging payment provider for order %s, amount %s %s",
                order.id, order.total_amount, order.currency)
    return {
        "provider_id": f"ch_fake_{order.id}",
        "status": "succeeded",
        "amount": str(order.total_amount),
    }


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_payment(self, order_id: str):
    """
    Process payment for a pending order.

    This task may be queued multiple times if:
      - The webhook fires more than once (Stripe guarantees at-least-once delivery)
      - A worker crashes mid-task and the task is retried by Celery
      - An ops engineer manually re-queues via the admin

    BUG: The check-then-act sequence below is not atomic. Two worker
    processes can both read status='pending', both pass the if-check,
    and both call charge_payment_provider() — resulting in a double charge.
    In production this happened 3 times in January (see FIN-401).
    The fix requires select_for_update() inside an atomic transaction.
    """
    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        logger.error("process_payment called with unknown order_id=%s", order_id)
        return

    if order.status != Order.STATUS_PENDING:
        logger.info(
            "Order %s is already %s, skipping payment.", order_id, order.status
        )
        return

    # ← RACE CONDITION: another worker can pass the check above simultaneously
    order.status = Order.STATUS_PROCESSING
    order.save(update_fields=["status", "updated_at"])

    try:
        provider_response = charge_payment_provider(order)

        order.status = Order.STATUS_PAID
        order.external_payment_id = provider_response["provider_id"]
        order.paid_at = timezone.now()
        order.save(update_fields=["status", "external_payment_id", "paid_at", "updated_at"])

        PaymentAttempt.objects.create(
            order=order,
            result=PaymentAttempt.RESULT_SUCCESS,
            provider_response=provider_response,
            amount_charged=order.total_amount,
        )

        logger.info("Payment succeeded for order %s", order_id)

    except Exception as exc:
        logger.error("Payment failed for order %s: %s", order_id, exc)

        PaymentAttempt.objects.create(
            order=order,
            result=PaymentAttempt.RESULT_FAILURE,
            provider_response={"error": str(exc)},
            amount_charged=order.total_amount,
        )

        order.status = Order.STATUS_FAILED
        order.save(update_fields=["status", "updated_at"])

        raise self.retry(exc=exc)
