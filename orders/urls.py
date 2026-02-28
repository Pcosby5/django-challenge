from django.urls import path
from .views import OrderListCreateView, OrderDetailView, order_summary, InternalOrderLookupView

urlpatterns = [
    path("orders/", OrderListCreateView.as_view(), name="order-list-create"),
    path("orders/<uuid:order_id>/", OrderDetailView.as_view(), name="order-detail"),
    path("orders/summary/", order_summary, name="order-summary"),
    path("internal/orders/", InternalOrderLookupView.as_view(), name="internal-order-lookup"),
]
