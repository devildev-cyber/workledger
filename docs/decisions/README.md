# Decision log

Significant product and technical decisions, one file per decision. A decision record explains what was decided and why, so later contributors don't have to guess or reopen settled questions.

## Adding a decision

1. Copy [`0000-template.md`](0000-template.md) to the next number, for example `0004-short-title.md`.
2. Fill it in and add it to the index below in the same pull request as the change it describes.
3. Never rewrite an accepted decision. To change course, add a new record and mark the old one **Superseded by** the new one.

## Index

| # | Decision | Status |
| --- | --- | --- |
| [0001](0001-record-decisions.md) | Record significant decisions in this log | Accepted |
| [0002](0002-pull-request-workflow.md) | Change `main` only through squash-merged pull requests | Accepted |
| [0003](0003-eslint-with-typescript-6.md) | Use ESLint with TypeScript 6.0 on the frontend | Accepted |
| [0004](0004-mvp-scope.md) | The MVP is Milestone B | Accepted |
| [0005](0005-accounts-and-memberships.md) | One account, many organization memberships | Accepted |
| [0006](0006-invitation-only-accounts.md) | Accounts are created by invitation only | Accepted |
| [0007](0007-email-interface.md) | Send email through a replaceable interface | Accepted |
| [0008](0008-property-scoped-managers.md) | Managers act only on properties assigned to them | Accepted |
| [0009](0009-session-authentication.md) | Server-side sessions with a cookie and a CSRF header | Accepted |
| [0010](0010-organization-scoped-access.md) | Organization in the URL, roles declared per endpoint | Accepted |
| [0011](0011-invitation-rules.md) | Invitation rules | Accepted |
| [0012](0012-password-reset.md) | Password reset | Accepted |
| [0013](0013-membership-administration.md) | Membership administration | Accepted |
| [0014](0014-frontend-api-access.md) | How the frontend talks to the API | Accepted |
| [0015](0015-property-directory.md) | Property directory | Accepted |
| [0016](0016-residents-and-tenancies.md) | Residents, move-ins, and private contact details | Accepted |
| [0017](0017-maintenance-requests.md) | Maintenance requests and what residents can see | Accepted |
| [0018](0018-attachments.md) | Attachments | Accepted |
| [0019](0019-work-orders-and-triage.md) | Work orders, triage, and the status lifecycle | Accepted |
| [0020](0020-dispatch-and-contractor-access.md) | Dispatch and what a contractor can see | Accepted |
