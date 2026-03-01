# FINDINGS

## Context

I inherited this Django codebase and prioritized production risk over breadth, following the 4–6 hour constraint.  
I started by restoring environment reliability, then fixed the highest-impact security/revenue/data-integrity issues, added regression tests, and made one architectural improvement.

## Priority Legend

- `P0`: Immediate security/revenue risk
- `P1`: High business/operational risk
- `P2`: Performance/maintainability risk

## 1) Missing App Migrations Blocked Bootstrapping (`P0`) — Fixed

**What I found**  
Running `migrate` failed with `django.db.utils.ProgrammingError: relation "users" does not exist`.

**How I found it**  
During first setup, `admin.0001_initial` failed because custom user model tables were not created yet.

**Impact**  
Fresh environments could not bootstrap, blocking local onboarding and CI/CD reliability.

**Fix**  
Created and applied initial migrations for `users` and `orders`, then verified with `showmigrations`.

**Priority rationale**  
This blocks all other work and production-like validation.

---

## 2) Payment Double-Charge Race Condition (`P0`) — Fixed

**What I found**  
`process_payment` in `orders/tasks.py` used non-atomic check-then-act logic.

**How I found it**  
Code review plus incident doc: `docs/postmortems/2024-01-19-double-charge-FIN-401.md`.

**Impact**  
Two workers could charge the same order simultaneously (direct revenue and trust impact).

**Fix**  
Added atomic claim logic using `transaction.atomic()` + `select_for_update()` before status transition to `processing`.

**Priority rationale**  
Known production incident with monetary impact.

---

## 3) Internal Order Lookup IDOR / RBAC Gap (`P0`) — Fixed

**What I found**  
Internal endpoint allowed any authenticated user to query any order.

**How I found it**  
Review of `InternalOrderLookupView` in `orders/views.py`.

**Impact**  
Sensitive order data exposure across customers.

**Fix**  
Enforced `IsAdminUser` for internal lookup endpoint.

**Priority rationale**  
Security and data privacy risk.

---

## 4) Order Creation Transaction Integrity (`P1`) — Fixed

**What I found**  
Order creation, line-item creation, and inventory decrement were not one atomic unit.

**How I found it**  
`orders/services.py` review (and comments referencing FIN-389 behavior).

**Impact**  
Could leave orphan orders or inconsistent inventory under failure/concurrency.

**Fix**  
Wrapped creation flow in `transaction.atomic()`, locked product row, and kept persistence + inventory update in the same transaction.

**Priority rationale**  
High data integrity risk affecting fulfillment and reporting.

---

## 5) Dashboard Summary Performance Issue (`P2`) — Fixed

**What I found**  
`get_orders_summary_for_user` loaded all orders into Python to count statuses.

**How I found it**  
Service-layer review and inline code comments.

**Impact**  
Poor scalability for users with many orders.

**Fix**  
Replaced Python loop with DB aggregation: `values("status").annotate(count=Count("id"))`.

**Priority rationale**  
Performance issue, lower severity than security/revenue bugs.

---

## 6) Decimal Precision Mismatch (`P1`) — Fixed

**What I found**  
Serializer precision for `total_amount` did not match model precision.

**How I found it**  
Compared serializer field config against model field (`max_digits=14, decimal_places=4`).

**Impact**  
Large monetary values could be mishandled at API serialization layer.

**Fix**  
Removed narrow custom serializer field and used model-backed precision consistently.

**Priority rationale**  
Financial data correctness.

---

## 7) Request Logging Memory Leak (`P1`) — Fixed

**What I found**  
Middleware appended per-request data to a module-level list that never cleared.

**How I found it**  
`core/middleware.py` review and inline incident notes.

**Impact**  
Unbounded memory growth, worker instability/OOM over time.

**Fix**  
Removed in-memory append behavior and retained structured logging only.

**Priority rationale**  
Operational stability risk.

---

## 8) N+1 Query Risk in Order List (`P2`) — Fixed

**What I found**  
List endpoint queried orders without related-object optimization.

**How I found it**  
Review of `OrderListCreateView.get`.

**Impact**  
Query amplification and slower response under larger datasets.

**Fix**  
Applied `select_related("customer")` and `prefetch_related("line_items__product")`.

**Priority rationale**  
Performance and scalability.

---

## 9) Tax Logic Placeholder Risk (`P1`) — Partially Fixed

**What I found**  
Tax handling is placeholder-based and not jurisdiction-accurate, as also noted in the Slack thread (`docs/slack-thread-2023-11-14-tax-issue.txt`).

**How I found it**  
Docs + service-layer logic review.

**Impact**  
Potential over/under-collection and compliance issues.

**Fix implemented in this phase**  
Applied short-term enterprise B2B policy (`enterprise` users taxed at `0.0000`) to align with documented interim business direction.

**Deferred**  
Full tax engine integration (e.g., TaxJar) remains architectural/product work outside this timebox.

---

## Architectural Improvement (Deliverable 3)

Refactored large `create_order` flow into a focused `OrderCreationService` with smaller methods for:
- product locking/validation
- pricing
- persistence
- inventory update
- notifications

`create_order(...)` remains as a compatibility wrapper, so API behavior did not change.

---

## Tests Added/Updated (Deliverable 4)

Added regression tests that would have caught key bugs:
- payment claim path uses locking and prevents duplicate charging behavior
- internal RBAC test verifies non-admin forbidden/admin allowed
- transactional rollback test ensures no orphan order if line-item persistence fails
- large amount serializer test prevents precision regression
- enterprise pricing expectation updated to reflect temporary zero-tax policy

All orders tests pass after changes.

---

## Infrastructure / Developer Experience Work Completed

- Added missing dependency wiring and stabilized environment bootstrap.
- Generated/applied missing `users` and `orders` migrations.
- Added admin registrations for core models to improve operational visibility.
- Added JWT auth endpoints to improve Postman/API testing workflow while preserving existing session-based behavior.

---

## Given More Time

1. Implement full tax engine integration and jurisdiction-aware tax policy.
2. Add stronger concurrency tests for true parallel task execution.
3. Add query-count assertions for performance regressions.
4. Reintroduce infrastructure-layer protections for internal endpoints (network allowlist/audit).
5. Remove deprecated `version` key from `docker-compose.yml` for cleaner runtime warnings.
