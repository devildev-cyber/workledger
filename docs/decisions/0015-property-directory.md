# 0015. Property directory

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

Every later phase refers to a place: a request is reported against a unit, a manager acts on certain properties, and an owner approves spending on a property. The directory is where those records are defined, so it also decides how much structure the rest of the product has to carry.

## Decision

- **Shape:** an organization has properties. A property may have buildings. A unit belongs to a property and, optionally, to a building. Buildings are a real record, because larger sites need them and small sites can simply have none.
- **Names:** a property name is unique within the organization, a building name is unique within its property, and a unit label is unique within its property and building, compared without regard to capitalization. Duplicates are refused with `409`.
- **Who may write:** only administrators create or change properties, buildings, and units.
- **Who may read:** administrators see every property. Managers see only the properties assigned to them ([0008](0008-property-scoped-managers.md)). A property outside that set looks like a missing one (`404`).
- **Manager assignment:** an administrator replaces the set of managers on a property as a whole. Only members who hold the manager role can be assigned. Removing the manager role from a member, or removing the member, clears their assignments.
- **Settings:** currency (three letters, default `USD`) and approval threshold (whole cents, optional) are stored on the property now. Nothing enforces them until Phase 7.
- **Record:** creating and changing these records writes activity events. Changes list the fields that changed with their before and after values.
- **Not included:** properties, buildings, and units cannot be deleted or archived yet. Records that later phases attach to them make deletion a decision of its own.

## Consequences

- Every query for a manager filters by their assigned property IDs, taken from the access context rather than from the request.
- Natural ordering ("2" before "10") is applied when units are listed.
- Renaming a building is supported by the API but has no screen yet.
- Property owners have no view of the directory until they have something to approve (Phase 7).
