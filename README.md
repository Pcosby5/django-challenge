# Backend Engineering Assessment

## Getting Started

**Requirements:** Docker + Docker Compose

```bash
# 1. Start all services (Django, Postgres, Redis, Celery worker)
docker compose up --build

# 2. In a separate terminal, run migrations and seed test data
make seed

# 3. The API is at http://localhost:8000
#    Import docs/finboard.postman_collection.json into Postman to explore it.
```

Test accounts (created by seed):

| Email                   | Password    | Tier        |
| ----------------------- | ----------- | ----------- |
| alice@acme.com          | password123 | pro         |
| bob@widgets.io          | password123 | free        |
| procurement@bigcorp.com | password123 | enterprise  |
| admin@finboard.io       | admin123    | staff/admin |

```bash
# Run the existing test suite
make test

# Open a Django shell
make shell
```

---

## What We'd Like From You

**Time budget:** Please don't spend more than 4–6 hours. We're not looking for a
full rewrite. We're looking for how you think and prioritise.

### Deliverable 1 — Written Bug Report (`FINDINGS.md`)

Before touching any code, write up what you find. For each issue:

- What is it?
- How did you find it?
- What is the production impact if left unfixed?
- What's your proposed fix?
- How would you prioritise it relative to the other issues you found?

Be direct. A one-paragraph description per issue is fine. We're not grading length.

### Deliverable 2 — Fixes

Fix the issues you believe are highest priority. You don't have to fix everything.
If you deliberately leave something unfixed, explain why in your bug report.

Your fixes should not break the existing test suite.

### Deliverable 3 — One Architectural Improvement

Pick one structural problem that isn't a simple bug something about how the
code is organised or designed and improve it. A focused, clean change is better
than a sweeping refactor.

Add a short note in your `FINDINGS.md` explaining what you changed and why.

### Deliverable 4 — Tests

Add tests that would have caught at least two of the bugs you fixed.
The existing tests must still pass.

---

## Codebase Overview

```
finboard/
├── orders/
│   ├── models.py       ← core data model
│   ├── views.py        ← DRF API views
│   ├── serializers.py  ← request/response serialization
│   ├── services.py     ← business logic
│   ├── tasks.py        ← async Celery tasks
│   └── tests/
├── users/
│   └── models.py       ← custom user model
├── core/
│   └── middleware.py   ← request logging
└── docs/               ← read these, they may be useful
```

---

## Submission

Push your changes to a GitHub repo and share access with us.
Include your `FINDINGS.md` at the root of the repo.

If there's anything you'd do differently with more time, note it briefly in
`FINDINGS.md` under a "Given More Time" section.

There are no trick questions. We just want to understand how you
think.

Good luck.
