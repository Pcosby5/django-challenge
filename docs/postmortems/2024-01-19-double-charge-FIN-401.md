# Incident Postmortem — FIN-401
# Date: 2024-01-19
# Severity: P1 (revenue impact)
# Author: Priya R.
# Status: OPEN — root cause not yet fixed in code

## Summary

Between 2024-01-15 and 2024-01-18, 3 customer orders were charged twice by
our payment provider (Stripe). Total duplicate charge value: $4,782.00.
All customers were refunded manually. Stripe flagged us for review.

## Timeline

- Jan 15 10:04 UTC — Stripe webhook fires for order FIN-ORD-88821
- Jan 15 10:04 UTC — Two Celery workers pick up process_payment simultaneously
                     (worker-3 and worker-7, both idle at time of delivery)
- Jan 15 10:04 UTC — Both workers read order status = 'pending'
- Jan 15 10:04 UTC — Both workers set status = 'processing' and call Stripe
- Jan 15 10:04 UTC — Two charges created: ch_ABC and ch_DEF for $1,189.00 each
- Jan 15 10:07 UTC — Customer emails support; support escalates
- Jan 15 10:41 UTC — Engineering manually cancels ch_DEF, issues refund

## Root Cause

`process_payment()` in `orders/tasks.py` performs a non-atomic check-then-act:

1. Read order.status
2. If pending → set to processing → charge Stripe

Steps 1→2 are not wrapped in a database transaction with row-level locking.
Two workers can both complete step 1 simultaneously before either completes
step 2, resulting in two charges.

## What Did NOT Work

- We thought Celery's `acks_late=True` would prevent this. It does not.
  acks_late delays acknowledgement until the task completes, but does not
  prevent concurrent execution across multiple workers.

- We considered a Redis lock (redlock). This adds complexity and a new
  failure mode. The correct fix is at the database layer.

## Correct Fix (not yet implemented)

Use `select_for_update()` inside an `atomic()` block:

```python
from django.db import transaction

with transaction.atomic():
    order = Order.objects.select_for_update().get(id=order_id)
    if order.status != Order.STATUS_PENDING:
        return  # another worker already claimed it
    order.status = Order.STATUS_PROCESSING
    order.save(update_fields=["status"])
# charge happens outside the lock
```

## Action Items

- [ ] FIN-401-1: Implement select_for_update fix in process_payment (unassigned)
- [x] FIN-401-2: Refund affected customers (done, Priya)
- [x] FIN-401-3: Add Stripe duplicate-charge alert (done, DevOps)
- [ ] FIN-401-4: Add regression test for concurrent task execution (unassigned)

## Open Questions

Should the charge happen inside or outside the DB transaction?
Charging inside means the transaction holds the DB lock open for the
duration of the HTTP call to Stripe (~300ms avg). Charging outside means
a crash between "mark processing" and "charge Stripe" leaves the order
stuck in 'processing'. Neither is perfect — see FIN-401 comments for
the thread on this.
