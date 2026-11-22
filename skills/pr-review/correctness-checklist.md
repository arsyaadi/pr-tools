# Correctness checklist (angles A and B)

Language- and framework-neutral. The repo's own written rules override any advice here.
Apply it to every line the PR adds or changes. Every finding needs its scenario: the concrete
input, state or execution order that makes it go wrong, what goes wrong, and the code that shows
it. "Could be a problem if …" without a path that reaches it is not a finding.

Check the first group first: those bugs cost the most and are the easiest to miss in a diff.

## First

- **Transaction boundaries.** Writes that must succeed or fail together but aren't in one
  transaction; a commit before a write that depends on it; an external call (HTTP, queue, email,
  payment) inside a transaction that can still roll back after the call went out. → One
  transaction, or an outbox / compensating step.
- **Idempotency.** A handler that can run twice for the same request (client retry, webhook or queue
  redelivery, double submit, a re-run job) and then charges, inserts, sends or increments twice. →
  An idempotency or unique key, an upsert, or a processed-check inside the same transaction.
- **State transitions.** A status or lifecycle change that doesn't check the current state (cancel
  a shipped order, pay a cancelled invoice), or a new state that existing `switch`es, guards or
  consumers don't handle. → Check the from-state in the write (`WHERE status = …`); handle the new
  state everywhere it's read.
- **Data integrity.** A write that can leave data inconsistent: a validation or constraint its
  siblings have and it lacks, orphaned children on delete, a uniqueness the code assumes but the
  schema doesn't enforce, a denormalized copy left stale. → The constraint, or the siblings'
  validation.

## Then

- **Contracts.** A changed function, endpoint, event or return value whose callers or consumers
  still expect the old one (shape, nullability, units, thrown errors, ordering, sync vs async).
  Check every caller at the PR head. → Update the callers, or keep the old contract.
- **Partial failure.** A multi-step operation (a loop of writes, a batch, calls to several services)
  that leaves half-done work when one step fails, with no rollback, retry or record of what failed;
  a `Promise.all`-style call whose one rejection hides the others' completed side effects. → Make
  it atomic, or record progress and resume.
- **Dates and time zones.** Local time where UTC is stored (or the reverse), a date-only value
  parsed as UTC midnight and shown a day off, DST gaps, month ends, inclusive vs exclusive range
  ends, comparing timestamps from different zones. → The repo's date helper, an explicit zone,
  half-open ranges.
- **Numbers.** Floats for money, integer division or truncation, rounding at the wrong step or with
  the wrong mode, overflow, string/number coercion. → Integer minor units or a decimal type; round
  once, at the end.
- **Backward compatibility.** Removing or renaming a field, endpoint, event, config key, enum value
  or serialized format that something outside this PR still reads: old clients, data cached or
  queued by the previous version, other services, the previous release during a rolling deploy. →
  Keep the old one until its readers have moved (expand, migrate, contract).
- **Races.** A non-atomic read-modify-write, a stale async response overwriting newer state, a
  check-then-act (TOCTOU), or shared mutable state without synchronization. Report one only when a
  concrete execution order produces incorrect behavior, and name that order. → An atomic update, a
  lock, a version check, or cancelling the stale request.
- **The usual.** Wrong logic or operator, off-by-one, an unhandled empty/null/undefined case, wrong
  API usage (check the installed version's signature), a missing `await`, data lost (overwritten,
  truncated, dropped on an error path).

## Persistence and migrations (only when the diff touches schema, migrations, queries or ORM models)

- A migration that breaks the code still running during the deploy: dropping or renaming a column
  or table the old release reads, adding `NOT NULL` without a default or backfill, changing a type
  in place. → Expand first, deploy, then contract in a later PR.
- A migration that locks or rewrites a large table (a non-concurrent index build, a full-table
  update or backfill in one statement) where the repo's other migrations avoid it. → The repo's
  pattern (concurrent index, batched backfill).
- A `down` migration that can't undo its `up`, where the repo's other migrations have working ones.
- A query whose meaning changed: a dropped `WHERE` (tenant, soft delete, status), a join that
  duplicates rows, a `NULL` compared with `=`.

Sources: Google Engineering Practices, "What to look for in a code review" (functionality,
concurrency); Martin Kleppmann, "Designing Data-Intensive Applications" (transactions,
idempotence); the expand/contract pattern for zero-downtime schema changes.
