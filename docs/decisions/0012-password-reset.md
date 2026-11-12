# 0012. Password reset

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

People forget passwords. Accounts are created by invitation ([0006](0006-invitation-only-accounts.md)) and email goes through a replaceable interface ([0007](0007-email-interface.md)), so a reset can work by emailing a link. The rules had to be settled so a reset cannot be used to find out who has an account or to take one over.

## Decision

- **Asking for a link:** `POST /api/auth/password-reset/request` always answers `202` with the same message, whether or not the email belongs to an active account. The email is sent only when it does.
- **Lifetime:** a link is valid for 60 minutes (configurable) and works once.
- **One link at a time:** asking again cancels any earlier unused link for that account.
- **Links:** the token is placed after `#` in the link (`/password-reset#token=...`), so browsers do not send it to servers. It is posted in a request body and stored only as a hash.
- **Choosing a password:** `POST /api/auth/password-reset/confirm` applies the normal password rules. A password that is too weak is refused without using up the link.
- **Failures:** unknown, expired, used, and deactivated-account links all give the same "not valid" answer.
- **After a reset:** every session of that account is ended, so anyone who had the old password is signed out. A "your password was changed" email is sent to the account address.
- **Record:** a `password_reset` event is stored without an organization, because the account is not tied to one.

## Consequences

- Whoever controls the mailbox controls the account. This is the same trust placed in invitations.
- The emailed link opens the browser app's `/password-reset` page.
- Email is sent after the change is saved. If sending fails, the reset still happened; the notice is lost.
- Repeated requests are not rate limited yet. That is listed with brute-force protection in Phase 10.
- Expired tokens stay in the table until a cleanup job exists, together with expired sessions.
