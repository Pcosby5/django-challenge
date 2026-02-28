"""
Management command to seed the database with realistic test data.
Run via: python manage.py seed_data
"""

import random
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from orders.models import Order, OrderLineItem, Product

User = get_user_model()


class Command(BaseCommand):
    help = "Seed the database with test data for the assessment"

    def handle(self, *args, **kwargs):
        self.stdout.write("Seeding database...")

        # Create users
        admin, _ = User.objects.get_or_create(
            email="admin@finboard.io",
            defaults={
                "username": "admin",
                "billing_tier": "enterprise",
                "company_name": "Finboard Internal",
                "is_staff": True,
                "is_superuser": True,
            },
        )
        admin.set_password("admin123")
        admin.save()

        alice, _ = User.objects.get_or_create(
            email="alice@acme.com",
            defaults={
                "username": "alice",
                "billing_tier": "pro",
                "company_name": "Acme Corp",
            },
        )
        alice.set_password("password123")
        alice.save()

        bob, _ = User.objects.get_or_create(
            email="bob@widgets.io",
            defaults={
                "username": "bob",
                "billing_tier": "free",
                "company_name": "Widgets Inc",
            },
        )
        bob.set_password("password123")
        bob.save()

        enterprise_user, _ = User.objects.get_or_create(
            email="procurement@bigcorp.com",
            defaults={
                "username": "bigcorp",
                "billing_tier": "enterprise",
                "company_name": "BigCorp Ltd",
            },
        )
        enterprise_user.set_password("password123")
        enterprise_user.save()

        # Create products
        products_data = [
            ("Starter Plan", "PLAN-STARTER", "49.99", 1000),
            ("Pro Plan", "PLAN-PRO", "199.99", 500),
            ("Enterprise Seat", "SEAT-ENT", "499.99", 200),
            ("API Credits (1000)", "CRED-1K", "9.99", 9999),
            ("Data Export Add-on", "ADDON-EXPORT", "29.99", 500),
            ("Premium Support", "SUPP-PREM", "799.99", 100),
            # Large-value product that will trigger the decimal truncation bug
            ("Enterprise Platform License", "LIC-ENT-PLAT", "150000.0000", 50),
        ]

        products = []
        for name, sku, price, inventory in products_data:
            p, _ = Product.objects.get_or_create(
                sku=sku,
                defaults={
                    "name": name,
                    "unit_price": Decimal(price),
                    "inventory_count": inventory,
                },
            )
            products.append(p)

        # Create orders for alice
        statuses = ["pending", "paid", "fulfilled", "failed"]
        for i in range(8):
            product = random.choice(products[:5])
            qty = random.randint(1, 5)
            subtotal = product.unit_price * qty
            tax = (subtotal * Decimal("0.08")).quantize(Decimal("0.0001"))
            total = subtotal + tax

            order = Order.objects.create(
                customer=alice,
                status=random.choice(statuses),
                total_amount=total,
                currency="USD",
                tax_amount=tax,
            )
            OrderLineItem.objects.create(
                order=order,
                product=product,
                quantity=qty,
                unit_price_snapshot=product.unit_price,
            )

        # Create a few orders for bob
        for i in range(3):
            product = products[0]
            order = Order.objects.create(
                customer=bob,
                status="pending",
                total_amount=Decimal("53.99"),
                currency="USD",
                tax_amount=Decimal("3.99"),
            )
            OrderLineItem.objects.create(
                order=order,
                product=product,
                quantity=1,
                unit_price_snapshot=product.unit_price,
            )

        self.stdout.write(self.style.SUCCESS("Done! Test credentials:"))
        self.stdout.write("  admin@finboard.io  / admin123   (staff)")
        self.stdout.write("  alice@acme.com     / password123 (pro tier)")
        self.stdout.write("  bob@widgets.io     / password123 (free tier)")
        self.stdout.write("  procurement@bigcorp.com / password123 (enterprise tier)")
