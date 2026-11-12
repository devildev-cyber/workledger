# 0011. Invitation rules

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

Accounts are created by invitation only ([0006](0006-invitation-only-accounts.md)). The rules for who may invite whom, how long an invitation lasts, and how existing accounts accept still had to be settled.

## Decision

- **Who invites:** administrators may invite any role. Managers may invite residents and contractors only. No other role may invite.
- **Visibility:** administrators see and revoke every invitation in the organization. Managers see and revoke only the invitations they sent.
- **Lifetime:** an invitation is valid for 7 days (configurable) and works once.
- **Re-inviting:** inviting an email address that already has a pending invitation to the same organization revokes the earlier one, so only the newest link works. Inviting a current member is refused.
- **New people:** accepting creates the account from the name and password they enter, adds the membership, and signs them in.
- **Existing accounts:** the person must be signed in to the account that owns the invited email. The link alone never adds a membership to an existing account.
- **Links:** the token is placed after `#` in the link, which browsers do not send to servers, and is posted to the API in a request body. It is stored only as a hash.
- **Failures:** unknown, expired, used, and revoked tokens all give the same "not valid" answer.

## Consequences

- Granting more powerful roles (administrator, manager, property owner) always needs an administrator.
- The emailed link opens the browser app's `/invitations/accept` page.
- Email is sent after the invitation is saved. If sending fails, the invitation exists but nobody was notified; re-inviting replaces it.
- Invitation acceptance reveals nothing about other accounts to people without a valid token.
