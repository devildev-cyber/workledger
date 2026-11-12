# 0006. Accounts are created by invitation only

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

WorkLedger holds resident and business information, and every user must belong to an organization to do anything. Open sign-up would create accounts with no legitimate access.

## Decision

- People join by accepting an invitation sent to their email address, setting their own password at that point.
- Invitations expire and can be used only once.
- The first organization and its first administrator are created with a command-line tool run by whoever operates the installation.
- Who may invite which roles is settled when invitations are built.

## Consequences

- There is no public sign-up page.
- Invitations depend on email (see [0007](0007-email-interface.md)).
- An existing user invited to a second organization gains a new membership rather than a new account (see [0005](0005-accounts-and-memberships.md)).
