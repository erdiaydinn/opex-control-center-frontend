# EAY Inventory W2W v13 Authority

W2W v13 extends the existing Inventory document, location, mission-attempt and immutable lease model. It does **not** introduce a competing campaign, assignment master, employee identity or client-owned count truth.

## One operator, one active location

An operator may own only one ACTIVE wall-to-wall location at a time.

- Ownership is derived from the latest immutable mission lease on ACTIVE attempts.
- Attempt creator identity is not treated as operator ownership because a supervisor may create a fresh unleased attempt during governed reassignment.
- An operator-scoped PostgreSQL advisory transaction lock serializes concurrent claims on different locations.
- A second lease for the same operator while another ACTIVE attempt is still owned fails closed.
- The current location must be completed or governed reassignment must supersede it before another location can be owned.
- Closed, abandoned and superseded attempts remain immutable historical evidence.

The database trigger is the final authority; client presentation cannot bypass the rule.

## Lost & Found is always last

`LOST_FOUND` is the reserved canonical W2W location id. PostgreSQL derives `location_kind=LOST_FOUND` from that identifier; the client does not submit location classification authority.

A Lost & Found attempt is rejected while either condition is true:

1. any STANDARD location lacks durable `LOCATION_COMPLETE` evidence; or
2. any STANDARD location still has an ACTIVE mission attempt.

Once every STANDARD location is durably complete and no STANDARD attempt remains active, Lost & Found may be opened. The W2W v11 closeout gate still requires every scoped location, including Lost & Found, to complete before document submission.

## Race and bypass resistance

The v13 invariants are enforced inside PostgreSQL:

- BEFORE INSERT attempt guard for Lost & Found ordering;
- BEFORE INSERT lease guard for one-operator/one-location;
- operator-scoped advisory transaction locking for cross-location races;
- existing one-active-attempt-per-document/location index;
- existing immutable attempt/lease/event history;
- existing tenant RLS and runtime role authority;
- existing v11/v12 scope freeze and closeout authority.

The dedicated exact-head CI gate applies the full Inventory migration chain on PostgreSQL 17, executes the source contract, proves the installed schema/trigger authority, rejects early Lost & Found, rejects a second active location for the same operator, completes two standard locations with durable event/lease evidence, then proves Lost & Found can open only after those standard locations are complete.

`production_activation_permitted=false`

`main_merge_permitted=false`
