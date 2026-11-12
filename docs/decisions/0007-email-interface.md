# 0007. Send email through a replaceable interface

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

Invitations and password reset need email in Phase 1, but local development and tests must not depend on paid or external services, and a production provider has not been chosen.

## Decision

- The backend sends email only through a small interface.
- Locally and in tests, an implementation records messages instead of sending them, so links can be followed during development and asserted in tests.
- A real provider is chosen and added during production readiness (Phase 10).
- Password reset is included in Phase 1.

## Consequences

- No email credentials are needed to develop or test WorkLedger.
- Phase 8 notifications reuse the same interface.
- Message content must never include secrets beyond the single-use link it exists to deliver.
