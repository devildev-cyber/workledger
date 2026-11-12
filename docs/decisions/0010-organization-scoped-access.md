# 0010. Organization in the URL, roles declared per endpoint

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

A user can belong to several organizations ([0005](0005-accounts-and-memberships.md)), and one organization must never see or affect another's data. Access rules need to be consistent, easy to review, and hard to forget.

## Decision

- Every endpoint that works on organization data lives under `/api/organizations/{organization_id}/...`. The organization is never implied by session state.
- A request resolves the signed-in user's membership in that organization. A non-member receives the same `404 Organization not found` as for an organization that does not exist.
- A member who lacks the needed role receives `403`.
- Each endpoint declares the roles allowed to use it with `require_roles(...)`; there are no implicit permissions, and administrators are not automatically allowed everywhere.
- Queries on organization data always filter by the organization from the request context, never by an ID supplied elsewhere in the request.
- Every member has a property scope ([0008](0008-property-scoped-managers.md)). Until properties exist, only administrators are unrestricted.

## Consequences

- Reviewers can check an endpoint's access rule by reading its declaration.
- Every new endpoint needs tests for a member with each role, a member of another organization, and a signed-out request.
- Records that belong to an organization must carry its ID so they can be filtered on.
- Endpoints that are not organization-scoped, such as sign-in and the current user, stay outside this path.
