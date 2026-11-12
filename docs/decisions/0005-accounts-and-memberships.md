# 0005. One account, many organization memberships

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

Independent contractors and some property owners work with several management firms. Requiring a separate login per firm is inconvenient, but organization data must stay strictly separated.

## Decision

- A **user account** belongs to a person, not to an organization, and has a single login.
- A **membership** links a user to one organization and carries that user's roles there. A user may have memberships in several organizations.
- Every action happens in the context of exactly one organization, and authorization is checked against the membership for that organization.

## Consequences

- A contractor serving two firms signs in once and switches between them; each firm sees only its own data.
- Every permission check needs both the user and the active organization.
- Tests must cover users with memberships in two organizations, not only users with one.
