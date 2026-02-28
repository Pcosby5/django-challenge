"""
Orders API views.

Endpoints:
  GET  /api/orders/                → list current user's orders
  POST /api/orders/                → create an order
  GET  /api/orders/<id>/           → retrieve a single order (owned by user)
  GET  /api/orders/summary/        → dashboard summary for current user
  GET  /api/internal/orders/       → [INTERNAL] admin order lookup — DO NOT EXPOSE
"""

import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Order
from .serializers import CreateOrderSerializer, OrderSerializer
from .services import create_order, get_orders_summary_for_user
from .tasks import process_payment

logger = logging.getLogger(__name__)


class OrderListCreateView(APIView):
    """
    GET  → paginated list of the authenticated user's orders
    POST → create a new order (kicks off async payment processing)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # BUG (N+1): OrderSerializer accesses order.customer.email for each
        # order in the list. Without select_related('customer'), this issues
        # one extra SQL query per order. With 500 active orders this endpoint
        # fires 501 queries on every page load.
        #
        # The original author added a TODO here in 2022 that was deleted
        # during a formatting sweep. The existing tests mock the queryset
        # so the issue is invisible in the test suite.
        queryset = Order.objects.filter(customer=request.user)
        serializer = OrderSerializer(queryset, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = CreateOrderSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            order = create_order(
                user=request.user,
                product_id=serializer.validated_data["product_id"],
                quantity=serializer.validated_data["quantity"],
                currency=serializer.validated_data.get("currency", "USD"),
                notes=serializer.validated_data.get("notes", ""),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        process_payment.delay(str(order.id))

        return Response(
            OrderSerializer(order).data,
            status=status.HTTP_201_CREATED,
        )


class OrderDetailView(APIView):
    """Retrieve a single order. Only the owning customer may access it."""

    permission_classes = [IsAuthenticated]

    def get(self, request, order_id):
        try:
            order = Order.objects.select_related("customer").prefetch_related(
                "line_items__product"
            ).get(id=order_id, customer=request.user)
        except Order.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response(OrderSerializer(order).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def order_summary(request):
    """Dashboard summary — returns order counts by status for the current user."""
    summary = get_orders_summary_for_user(request.user)
    return Response(summary)


class InternalOrderLookupView(APIView):
    """
    INTERNAL endpoint used by the ops dashboard to look up any order by ID.

    Originally this was protected by VPN + IP allowlist. That was removed
    in a infra migration in March 2023 and never replaced (FIN-388).

    BUG (IDOR): This endpoint trusts the `order_id` query param and returns
    the order to ANY authenticated user — not just admins or the order owner.
    A regular customer can enumerate any other customer's order details,
    including their email, order value, and payment IDs, by iterating UUIDs.

    This should be restricted to IsAdminUser at minimum. The real fix
    is to also scope the queryset to owned orders or add explicit ownership
    checks, and to reinstate the IP allowlist at the infrastructure layer.
    """

    permission_classes = [IsAuthenticated]  # BUG: should be IsAdminUser

    def get(self, request):
        order_id = request.query_params.get("order_id")
        if not order_id:
            return Response(
                {"detail": "order_id query param is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # BUG: no ownership check — any authenticated user can read any order
            order = Order.objects.select_related("customer").prefetch_related(
                "line_items__product"
            ).get(id=order_id)
        except Order.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response(OrderSerializer(order).data)
