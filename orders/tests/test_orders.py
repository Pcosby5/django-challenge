"""
Tests for the orders app.

These tests were written alongside the initial implementation.
They pass on CI but provide a false sense of security — several
critical bugs in views.py, tasks.py, and serializers.py are not covered.
"""

import uuid
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest
from django.contrib.auth import get_user_model

from orders.models import Order, Product, OrderLineItem
from orders.serializers import OrderSerializer
from orders.services import create_order, get_orders_summary_for_user

User = get_user_model()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="alice",
        email="alice@example.com",
        password="password123",
        billing_tier="free",
    )


@pytest.fixture
def enterprise_user(db):
    return User.objects.create_user(
        username="corp",
        email="corp@bigco.com",
        password="password123",
        billing_tier="enterprise",
    )


@pytest.fixture
def product(db):
    return Product.objects.create(
        name="Widget Pro",
        sku="WGT-001",
        unit_price=Decimal("99.99"),
        inventory_count=100,
    )


@pytest.fixture
def pending_order(db, user, product):
    order = Order.objects.create(
        customer=user,
        status=Order.STATUS_PENDING,
        total_amount=Decimal("107.99"),
        currency="USD",
        tax_amount=Decimal("8.00"),
    )
    OrderLineItem.objects.create(
        order=order,
        product=product,
        quantity=1,
        unit_price_snapshot=product.unit_price,
    )
    return order


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------

class TestCreateOrder:
    def test_creates_order_successfully(self, db, user, product):
        order = create_order(user, product.id, quantity=2)

        assert order.status == Order.STATUS_PENDING
        assert order.customer == user
        assert order.line_items.count() == 1

    def test_raises_on_inactive_product(self, db, user, product):
        product.is_active = False
        product.save()

        with pytest.raises(ValueError, match="inactive"):
            create_order(user, product.id, quantity=1)

    def test_raises_on_insufficient_inventory(self, db, user, product):
        with pytest.raises(ValueError, match="Insufficient inventory"):
            create_order(user, product.id, quantity=9999)

    def test_enterprise_discount_applied(self, db, enterprise_user):
        """Enterprise users get 10% off orders over $10,000."""
        big_product = Product.objects.create(
            name="Enterprise Suite",
            sku="ENT-001",
            unit_price=Decimal("5000.00"),
            inventory_count=10,
        )
        order = create_order(enterprise_user, big_product.id, quantity=3, currency="USD")

        # Subtotal 15000, discount 10% → 13500, enterprise tax policy → 0
        assert order.tax_amount == Decimal("0.0000")
        assert order.total_amount == Decimal("13500.0000")

    def test_inventory_decremented_after_order(self, db, user, product):
        initial = product.inventory_count
        create_order(user, product.id, quantity=3)
        product.refresh_from_db()
        assert product.inventory_count == initial - 3

    @patch("orders.services.OrderLineItem.objects.create")
    def test_rolls_back_order_when_line_item_create_fails(self, mock_line_item_create, db, user, product):
        """
        Regression for FIN-389: a line-item failure must not leave an orphan order.
        """
        mock_line_item_create.side_effect = Exception("line item write failed")
        initial_inventory = product.inventory_count

        with pytest.raises(Exception, match="line item write failed"):
            create_order(user, product.id, quantity=2)

        assert Order.objects.filter(customer=user).count() == 0
        product.refresh_from_db()
        assert product.inventory_count == initial_inventory


class TestOrderSummary:
    def test_returns_counts_by_status(self, db, user, product):
        Order.objects.create(
            customer=user, status="pending",
            total_amount=Decimal("100"), currency="USD", tax_amount=Decimal("8"),
        )
        Order.objects.create(
            customer=user, status="pending",
            total_amount=Decimal("100"), currency="USD", tax_amount=Decimal("8"),
        )
        Order.objects.create(
            customer=user, status="paid",
            total_amount=Decimal("200"), currency="USD", tax_amount=Decimal("16"),
        )
        summary = get_orders_summary_for_user(user)
        assert summary["pending"] == 2
        assert summary["paid"] == 1

    def test_returns_empty_dict_for_new_user(self, db, user):
        assert get_orders_summary_for_user(user) == {}


# ---------------------------------------------------------------------------
# Serializer tests
# ---------------------------------------------------------------------------

class TestOrderSerializer:
    def test_serializes_order(self, db, pending_order):
        data = OrderSerializer(pending_order).data
        assert data["status"] == "pending"
        assert data["currency"] == "USD"

    def test_customer_email_included(self, db, pending_order):
        data = OrderSerializer(pending_order).data
        assert data["customer_email"] == "alice@example.com"

    def test_large_total_amount_serializes_without_precision_loss(self, db, user):
        order = Order.objects.create(
            customer=user,
            status=Order.STATUS_PENDING,
            total_amount=Decimal("1234567.8912"),
            currency="USD",
            tax_amount=Decimal("0.0000"),
        )
        data = OrderSerializer(order).data
        assert data["total_amount"] == "1234567.8912"


# ---------------------------------------------------------------------------
# View tests  (these use mocked querysets and miss the real query behaviour)
# ---------------------------------------------------------------------------

class TestOrderListView:
    """
    These tests mock the queryset, so they do NOT catch the N+1
    query issue in the real view. They test HTTP wiring only.
    """

    def test_unauthenticated_request_rejected(self, client):
        response = client.get("/api/orders/")
        assert response.status_code in (401, 403)

    def test_authenticated_user_sees_their_orders(self, client, db, user, pending_order):
        client.force_login(user)
        response = client.get("/api/orders/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == str(pending_order.id)

    def test_user_cannot_see_other_users_orders(self, client, db, user, enterprise_user, pending_order):
        client.force_login(enterprise_user)
        response = client.get("/api/orders/")
        assert response.status_code == 200
        assert response.json() == []


class TestOrderDetailView:
    def test_owner_can_access_order(self, client, db, user, pending_order):
        client.force_login(user)
        response = client.get(f"/api/orders/{pending_order.id}/")
        assert response.status_code == 200

    def test_non_owner_cannot_access_order(self, client, db, enterprise_user, pending_order):
        client.force_login(enterprise_user)
        response = client.get(f"/api/orders/{pending_order.id}/")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Internal endpoint RBAC tests
# ---------------------------------------------------------------------------

class TestInternalOrderLookupView:
    def test_regular_user_forbidden(self, client, db, user, pending_order):
        client.force_login(user)
        response = client.get(f"/api/internal/orders/?order_id={pending_order.id}")
        assert response.status_code == 403

    def test_staff_user_can_access(self, client, db, pending_order):
        staff = User.objects.create_user(
            username="ops",
            email="ops@finboard.io",
            password="password123",
            billing_tier="pro",
            is_staff=True,
        )
        client.force_login(staff)

        response = client.get(f"/api/internal/orders/?order_id={pending_order.id}")
        assert response.status_code == 200
        assert response.json()["id"] == str(pending_order.id)


# ---------------------------------------------------------------------------
# Task tests
# ---------------------------------------------------------------------------

class TestProcessPaymentTask:
    @patch("orders.tasks.Order.objects.select_for_update")
    def test_claim_order_uses_select_for_update(self, mock_select_for_update, db, pending_order):
        """
        Regression guard for FIN-401:
        payment claim path must use row-level locking.
        """
        locked_qs = MagicMock()
        locked_qs.get.return_value = pending_order
        mock_select_for_update.return_value = locked_qs

        from orders.tasks import _claim_order_for_processing
        claimed = _claim_order_for_processing(str(pending_order.id))

        assert claimed is not None
        assert claimed.status == Order.STATUS_PROCESSING
        mock_select_for_update.assert_called_once()
        locked_qs.get.assert_called_once_with(id=str(pending_order.id))

    @patch("orders.tasks._claim_order_for_processing")
    @patch("orders.tasks.charge_payment_provider")
    def test_skips_when_order_not_claimed(self, mock_charge, mock_claim, db, pending_order):
        mock_claim.return_value = None

        from orders.tasks import process_payment
        process_payment(str(pending_order.id))

        mock_charge.assert_not_called()

    @patch("orders.tasks.charge_payment_provider")
    def test_pays_pending_order(self, mock_charge, db, pending_order):
        mock_charge.return_value = {
            "provider_id": "ch_test_123",
            "status": "succeeded",
            "amount": "107.99",
        }
        from orders.tasks import process_payment
        process_payment(str(pending_order.id))

        pending_order.refresh_from_db()
        assert pending_order.status == Order.STATUS_PAID
        mock_charge.assert_called_once()

    @patch("orders.tasks.charge_payment_provider")
    def test_skips_already_processed_order(self, mock_charge, db, pending_order):
        """
        This test appears to verify idempotency but it runs in a single
        thread, so it does NOT catch the race condition that occurs when
        two Celery workers process the same order simultaneously.
        """
        pending_order.status = Order.STATUS_PAID
        pending_order.save()

        from orders.tasks import process_payment
        process_payment(str(pending_order.id))

        mock_charge.assert_not_called()

    @patch("orders.tasks.charge_payment_provider")
    def test_duplicate_invocation_charges_once(self, mock_charge, db, pending_order):
        """
        Sequential idempotency check: duplicate delivery should not
        create duplicate provider charges after first success.
        """
        mock_charge.return_value = {
            "provider_id": "ch_test_123",
            "status": "succeeded",
            "amount": "107.99",
        }
        from orders.tasks import process_payment
        process_payment(str(pending_order.id))
        process_payment(str(pending_order.id))

        mock_charge.assert_called_once()
