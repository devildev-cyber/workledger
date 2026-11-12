# 0016. Residents, move-ins, and private contact details

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

A resident is a person the firm houses, who may or may not have signed in yet. The firm needs to record who lives where and when, keep their contact details private, and let residents see their own home without exposing anyone else.

## Decision

- **Two records:** a **resident** is the person, with a name and optional email, phone, and access instructions. A **tenancy** places a resident in a unit from a move-in date, with an optional move-out date. People are never copied per unit, so a resident who moves keeps one record and a full history.
- **Many to many:** a unit can have several current residents, and a resident can have several tenancies, including in different units at once. Overlapping tenancies for the same resident and unit are refused with `409`. A move-out cannot be before the move-in.
- **Current:** a tenancy is current when today falls from the move-in date to the move-out date, or the move-out date is not set.
- **Linking to an account:** a resident record links to a user when the emails match and the user holds the resident role in the same organization. This happens when the resident is created, when their email changes, and when they accept an invitation. A resident without an account is a normal record.
- **Private details:** email, phone, and access instructions are returned only to administrators and to managers, and a manager sees a resident only through a tenancy in one of their assigned properties. Residents never receive other people's records. Property owners and contractors receive none.
- **Resident view:** `GET /my-home` lists the signed-in resident's current homes with address, building, unit, and move-in date. It contains no other resident and no private fields.
- **After a move-out:** the person stops seeing the unit in My home. Requests they submitted while living there remain theirs to read (applied in Phase 3). They gain no access to later requests for that unit.
- **Activity:** events for residents record the name or the names of the changed fields, never the contact values, so the activity record does not become a second copy of private data.
- **Who may write:** only administrators create or change residents and tenancies. Managers have read access to the residents of their properties.

## Consequences

- Managers cannot yet add a resident themselves. If that proves slow in practice, widening the rule is a small change to one dependency.
- Residents who have no matching unit see a message telling them to contact their property manager.
- Residents are not deleted. Removing a person from a unit is a move-out.
- The seed data uses reserved example domains and `555-01xx` phone numbers.
