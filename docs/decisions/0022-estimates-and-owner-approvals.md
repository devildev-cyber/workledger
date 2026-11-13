# 0022. Estimates and owner approvals

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

A property sets a spending limit so that large repairs are not committed without the owner knowing. A limit that only the screen respects is not a limit: the contractor's app, a manager's shortcut or a direct status change would walk around it. The rule has to live where every change to a work order passes through, and each decision has to stay on record with who made it, when, for how much, and why.

## Decision

**Who decides**

- A property owner decides on estimates above the property's approval threshold, and only at the properties an administrator has given them (`PUT /properties/{id}/owners`). Only members with the property owner role can be given a property, and losing the role or leaving the organization ends the ownership.
- Managers and administrators record estimates but never decide on them. An estimate at or below the threshold needs nobody: it is recorded as *no approval needed*. The threshold itself is allowed; one cent more is not. A property with no threshold never asks for approval.
- Nobody decides on an estimate they recorded themselves (`403`). This matters when one person holds both the manager and owner roles.
- If a property has no owner, an estimate above the threshold simply waits. The work order page says so ("No property owner is set"), because letting a manager or administrator decide instead would defeat the gate.

**Estimates**

- An estimate is one amount in whole cents, in the property's currency, with a description of what it covers and an optional "quoted by". Amounts from 1 cent to 10,000,000,000.00 are accepted.
- Managers record estimates, not contractors. Costs stay staff-only ([decision 0021](0021-verification-and-closure.md)), and a contractor never sees an amount or an estimate entry. A contractor submitting a quote themselves is deferred.
- Estimates are never edited. A revision is a new estimate that replaces the current one. Every version, its amount, and its decision stay on record, so one work order can show 80,000 rejected, then 65,000 approved. There is no list of competing estimates: a work order is held to one estimate at a time.
- The threshold and the "needs approval" answer are stored with the estimate when it is recorded, so lowering the threshold later does not rewrite history.
- An estimate can be recorded while the work order is open, assigned, in progress, on hold, or awaiting approval. Once the work is ready for review, finished, or cancelled it cannot.

**The gate**

- Above the threshold, the estimate is *pending* and the work order moves to *awaiting approval*. It remembers where it was.
- The gate is one check inside `change_status`, which every status change in the system passes through: the manager's status route, the contractor's job route, verification, reassignment, and the seed. While the current estimate needs approval and has not been approved, no move into *in progress*, *ready for review*, or *completed* is allowed, including a reopening. The `system` and `review` options that exist for dispatch, approvals and verification are not ways around it.
- Cancelling and reopening does not clear the hold. The estimate is still pending, and work still cannot start.
- The refusal is `409` and its wording names no amounts, because a contractor can see it.
- Verification does not look at the gate separately; it is refused because it needs the move to *completed*.

**What a decision does**

- **Approve** (reason optional): the work order goes back to the status it had before, unless a contractor has since left, in which case it goes back to open.
- **Reject** (reason required): the work order goes on hold. A manager can then record a revised estimate to ask again (above the threshold it is pending again, below it nobody needs to decide) or cancel the work order. The rejected estimate keeps blocking work until one of those happens.
- A revised estimate that no longer needs approval releases the work immediately.
- A decision is made once. An estimate that has been replaced, or whose work order is finished or cancelled, cannot be decided (`409`).
- Each decision adds an entry to the work order's history (approved or rejected, with the reason) and an activity event holding the actor, the time, the amount, the currency and the reason. The estimate itself stores who decided, when, and why.

**When the work costs more than the estimate**

- Verification is never refused over cost, because the money is already spent and refusing would only hide it. Instead, the *verified* history entry and the activity event record a cost check: the estimate, how far the final cost went over it, and whether the final cost is above the threshold with no approved estimate that covers it.
- The work order page shows these as warnings in the outcome.
- This is the known limit of the design. An estimate is optional, so work done without recording one is not held. The cost check is what makes that visible afterwards.

**What an owner sees**

- The owner's workspace lists the estimates that needed a decision at their properties, and opens one with: the property and its address, the location, the work requested (the scope), kind, priority and due date, the amount, the description, who quoted it, the threshold, and every earlier estimate for that work with its decision.
- An owner never receives the internal record: no notes, history, files, residents, contractors, or final costs. They have no access to work orders, requests, or the directory. An estimate at a property they do not own looks missing (`404`).

## Consequences

- Owners are given properties by an administrator on the property page, in the same way managers are.
- Because the gate sits in `change_status`, any later feature that changes status gets it for free. A feature that bypasses `change_status` would bypass the gate, so none may.
- The estimate form is for managers. If contractors should quote on their own, that is a later addition that creates the same records.
- Estimates are in the property's currency only. Nothing is converted.
- Notifications ([Phase 8](../../ROADMAP.md#phase-8--notifications-and-activity)) will tell an owner when an estimate waits for them. Until then they see it on their Approvals page.
