# 0008. Managers act only on properties assigned to them

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

The product's least-privilege rule says managers act within their assigned organization and properties. Larger firms split portfolios between managers.

## Decision

- Administrators see and act on every property in their organization.
- Managers see and act only on the properties assigned to them.
- Phase 1 builds permission checks that accept a property scope. Assigning managers to properties is built in Phase 2, once properties exist.

## Consequences

- Very small firms must assign every property to their managers; the interface should make that quick.
- Queues, searches, and reports must apply the property scope, not only single-record endpoints.
