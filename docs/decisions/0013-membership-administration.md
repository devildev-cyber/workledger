# 0013. Membership administration

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

Invitations add people to an organization ([0011](0011-invitation-rules.md)). The organization also needs a way to see who belongs to it, change what they may do, and remove them. Roles decide what a member can do, so this is where an organization could lock itself out or hand out power by mistake.

## Decision

- **Who:** only administrators may list members, change roles, or remove members. Managers do not see the member list.
- **Roles:** a member's roles are replaced as a whole set, and at least one role is required. Saving the same set changes nothing and records nothing.
- **Last administrator:** the last administrator cannot lose the role and cannot be removed. The request is refused with `409`. An administrator may step down or leave once another administrator exists.
- **Removing:** removing deletes the membership only. The person's account and their other organizations are untouched. Their open sessions lose access to this organization at once, because access is checked against the membership on every request.
- **Addressing:** members are addressed by membership ID inside the organization's URL. A membership ID from another organization gives the same `404` as one that does not exist.
- **Record:** role changes and removals are stored as activity events with the roles before and after, and the administrator who acted.
- **Concurrency:** the check for the last administrator runs after locking the organization row, so two administrators demoting each other at the same moment cannot leave none. SQLite has no row locks and serializes writers instead.

## Consequences

- Role changes take effect on the member's next request. No sign-out is needed.
- Removing a member does not cancel invitations they sent. Those are handled with invitations.
- When property assignments arrive in Phase 2, removing a membership must also remove the member's assignments.
- Deactivating an account is a separate action, not part of this task.
- Only administrators can remove members, so a member cannot leave on their own yet.
