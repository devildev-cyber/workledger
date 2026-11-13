# 0021. Verifying work, recording the outcome, and closing

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

A contractor saying "done" is a claim, not a result. A manager needs to check it, say what was actually done, record what it cost, and either accept it or send it back. Whatever they decide has to stay on record, because later phases (reports, owner approvals) read costs and outcomes from here.

## Decision

**The review**

- Work marked *ready for review* leaves that status in exactly two ways, and a plain status change is refused for both (`409`):
  - **Verify**: the work order becomes *completed*, with a resolution and an optional final cost.
  - **Send back**: the work order returns to *in progress*, with a reason the contractor reads.
- Only an administrator or a manager at the property can review. A contractor, resident, or owner gets `403`, and a record outside a manager's properties looks missing (`404`).
- Only work that is ready for review can be verified or sent back. Every check runs before anything changes, so a refused review leaves the work order and its history as they were.
- Closing is a separate step: *completed* to *closed*. It needs a recorded resolution, so a work order cannot be closed without having been verified.

**What is recorded**

- **Resolution**: required, 3 to 2,000 characters, in the manager's words. It is separate from the contractor's note, which stays in the history as written.
- **Final cost**: optional. It is stored as a whole number of minor units (cents), never as a floating-point number, and can be zero. A blank cost means "not recorded", which is different from zero. Amounts up to 10,000,000,000.00 are accepted.
- **Currency**: a three-letter code. It defaults to the property's currency and is stored with the cost, so a figure is never separated from its currency. It is empty when there is no cost.
- Who verified and when are stored on the work order. Times are stored in UTC.
- The history gets a *verified* entry holding the resolution and the cost, and a status change to completed. A send back adds a *sent back* entry holding the reason. Each review is also written to the activity log.

**Reopening**

- Moving a completed or closed work order back to in progress clears its current outcome (resolution, cost, currency, verifier), so a total never counts work that is no longer finished. The history keeps every earlier verification, so reopening and verifying again leaves two *verified* entries.
- A completed work order can be reopened by a manager. A closed one only by an administrator, as before.

**What each person sees**

- The resident is told only the status. Verifying sets their request to *resolved* and closing sets it to *closed*. The resolution and cost are never sent to them, and neither is a message.
- The contractor sees that the job is completed. They never see the resolution, the cost, or the verification entry. A send-back reason is written for them, so they do see it, shown as coming from the "Property team".
- The review box shows the manager the contractor's finishing note and how many photos and documents are attached. Evidence is not required to verify: a manager may reasonably accept a job with no photo, and a blocking rule would only teach people to attach junk. The count makes its absence visible.

**Maintenance history**

- The property page lists work that was verified (completed or closed), newest first, with its cost, and can be narrowed to one unit. Cancelled work is left out.
- It uses the work order list with `history_only` and `unit_id` filters, so it follows the same property scoping as everything else. A manager sees only the properties they look after.

## Consequences

- Residents are informed, not asked. If the problem is not fixed they can message staff, and a manager can reopen the work order. A confirmation step can be added later without changing this.
- Costs are staff-only. Owners will see an estimate and a decision in Phase 7, not these figures.
- A cost recorded in one currency is not converted. Reports (Phase 9) must group by currency.
- The contractor's own invoice or quote is not recorded yet. Estimates arrive in Phase 7.
