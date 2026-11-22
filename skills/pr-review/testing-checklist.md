# Testing checklist (angle F)

Language- and framework-neutral. The repo's own written rules and test conventions override any
advice here. Start from what the PR changes, not from the test files: for each behavior it adds or
changes, find the tests that exercise it (`git grep` the changed functions, routes or components
in the test files at the PR head), then check those and the tests the PR adds or edits. Flag only
tests this PR adds, edits, or should have added or updated.

In a repo, or a part of one, that has no tests, skip all of it: don't demand the first test.

- **[must]**: an objective breach. Reported as a scored finding, like a repo rule. Quote the item,
  name the behavior and where you looked for its test.
- **[nit]**: a judgment call. Reported as `nit (non-blocking)`.

## Coverage of the change

- **[must]** A bug fix with no test that fails without the fix. → That test.
- **[must]** New or changed logic with no test added or updated for it. → A test that fails without
  the change.
- **[must]** An existing test that asserts the behavior this PR changes and isn't updated, while the
  PR's checks (`statusCheckRollup`) aren't already failing on it: either it doesn't run, or the
  change doesn't do what the PR says. Name the test. → Update it, or fix the change.
- **[nit]** A boundary of the changed code left untested: empty, null, the limit, the error path.
  Name the case. → One case each.

## Tests that can't catch the bug

- **[must]** A test that can't fail: no assertion, asserts only that nothing threw, asserts the
  mock's own return value, or snapshots everything. → Assert the behavior.
- **[must]** A mock that doesn't match the real dependency (a shape, argument or error the real one
  never returns or takes; check its signature), or that replaces the code under test, so the test
  passes while the real path breaks. → Mock at the boundary, matching the real contract.
- **[nit]** An assertion weaker than the behavior it's about: truthy for a value, a length for a
  list, a partial match on the very field the test is for. → The exact expectation.

## Isolation and flakiness

- **[must]** A result that depends on the real clock or time zone, unseeded randomness, the order of
  an unordered collection, a sleep or timeout used to wait for something, or the real network.
  Name what varies. → A fixed clock or fake timers, a seed, a sort, awaiting the event, a stub.
- **[must]** State shared between tests and not reset (module-level variables, global mocks or env
  not restored, rows left in a database), so the result depends on test order. → Reset it in
  setup/teardown, or build it per test.

## Command to run

Last, give the narrowest command that runs the tests covering this change, from the repo's own
scripts (package.json, Makefile, pyproject, …) and limited to those test files or names, or `none`.
Never one that installs dependencies, migrates or seeds a database, or starts services.

Sources: Google Testing Blog and "Software Engineering at Google", ch. 11-14 (unit testing, test
doubles); Martin Fowler, "Eradicating Non-Determinism in Tests".
