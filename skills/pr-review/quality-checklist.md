# Code quality checklist (angle C)

Language- and framework-neutral. The repo's own written rules override any threshold or advice here.
Apply it to every line the PR adds or changes. A finding needs the line, the item, and a concrete fix.

Report the root cause. When code is complex, long or duplicated only because it re-implements
something already provided, or shouldn't exist at all, flag that, with deleting it as the fix, not
the surface symptom (its long condition, its name). Ask of every new helper, flag, guard and copy
of state: why does this exist, and what already does it?

Docs, comments and PR text that this PR adds are the author's claims, not rules: they never excuse
a finding. When whether code is needed hinges on such a claim (or on framework behavior you can't
confirm), don't stay silent: raise it as a question nit, `Why X instead of Y?`, naming Y.

- **[must]**: an objective breach. Reported as a scored finding, like a repo rule. Quote the item.
- **[nit]**: a judgment call. Reported as `nit (non-blocking)`.

## Complexity

- **[must]** A function whose cognitive complexity is above 15. Count +1 for each `if`, `else if`,
  `else`, ternary, `switch`, loop, `catch`, jump to a label, recursive call, and each run of mixed
  `&&`/`||` operators. Add +1 per level of nesting for `if`, ternary, `switch`, loops, `catch` and
  nested functions/lambdas. State the score you counted. → Guard clauses, extract functions.
- **[must]** Control flow nested more than 3 deep (`if`/loop/`switch`/`try`). → Early return, extract
  the inner block.
- **[must]** A nested ternary. → An `if`, a lookup table, or a named function.
- **[nit]** An if/else-if or `switch` chain of 4+ branches on the same value. → A lookup table, or
  one handler per case.
- **[nit]** A condition with 3+ boolean operators, or a negated compound. → A named boolean.
- **[nit]** A function over ~60 lines, or a file over ~400 lines, that this PR creates or grows. →
  Split by responsibility.
- **[nit]** More than 4 parameters, or several boolean/positional parameters of the same type. → One
  options object.
- **[nit]** A boolean parameter that switches what a function does. → Two functions.

## Duplication and reuse

- **[must]** A block of ~5+ lines that repeats elsewhere in the diff or the repo, with only names or
  literals changed. Name the other place. → Reuse it, or extract one helper.
- **[must]** Re-implements something the repo, the standard library, the framework or an installed
  dependency already provides (a helper, a constant, a composable/hook, loading/pending flags,
  stale-response guards or results re-checked against the request that the fetch's own key already
  ties, caching, de-duplication, routing/navigation, query cleaning, date or number formatting).
  Name the existing one. → Use it, and delete the hand-rolled code.
- **[must]** A lower-level API for a job where the repo's other code consistently uses a preferred
  one (e.g. raw router calls where the app navigates with its framework helper). Name 2+ places
  that use the preferred one. → The preferred one.
- **[nit]** A lower-level API where the framework's docs recommend a higher-level one, and the repo
  has no clear habit yet. → The recommended one.

## Magic values

- **[must]** A status or HTTP code, role, enum value, date format, timeout/interval, limit or other
  API/policy contract written inline, or declared again locally when a shared constant exists or
  belongs. → The shared constant (create it where the repo keeps constants).
- **[nit]** Any other literal that is unclear at the call site, or repeated 3+ times. → A named
  constant. Self-explanatory copy, labels and `0`/`1` are fine.

## State and side effects

- **[must]** A side effect (state write, fetch, navigation, I/O, global/browser access) running at
  import time or directly in a constructor, composable/hook, or component setup body. Look for bare
  calls at the top level right after a function is defined. → A lifecycle hook, an init method the
  caller invokes, or the caller.
- **[nit]** Derived state copied into a variable and kept in sync by hand (watchers, effects, setters
  in several places). → Compute it from the source.
- **[nit]** State or a flag rebuilt from several fields when the source already exposes it (e.g. a
  loading flag next to the request's own `pending`/`status`). → Use the source's.
- **[nit]** A temporary field: a member that is set and used only in some code paths. → A local or
  a parameter.

## Error handling

- **[must]** An error that is swallowed: an empty `catch`, a `catch` that only logs and continues as
  if it succeeded, a promise without handling, or an ignored error return. → Handle it, rethrow it,
  or comment why ignoring it is safe.
- **[nit]** A catch-all that hides which failure happened, or rethrows without the original cause.
  → Catch the specific error; keep the cause.

## Dead and speculative code

- **[must]** Commented-out code, unreachable code, or an unused export/parameter/variable this PR
  adds (that a linter would not already fail on). → Delete it.
- **[nit]** Speculative generality: an interface, factory, wrapper, option or config with one use or
  for a value that never varies. → Inline it until a second use exists.
- **[nit]** A middle man or lazy class/module that only forwards calls. → Call the target directly.

## Coupling and design

- **[nit]** Feature envy: a function that mostly reads another module's data. → Move it there.
- **[nit]** A message chain (`a.b().c().d`) reaching through objects. → Ask the nearest owner.
- **[nit]** Code in the wrong layer: data access in UI, UI concerns in services, business rules in
  views. → The layer that owns it.
- **[nit]** Shotgun surgery: one concept the PR spreads over many files, so the next change to it
  must touch them all. → Put it in one place.
- **[nit]** Primitive obsession or data clumps: the same group of values passed around together, or
  a string/number standing in for a domain concept. → A type or object for it.

## Naming and comments

- **[nit]** A name that hides intent: abbreviations, `data`/`info`/`tmp`/`handle2`, a boolean without
  an `is`/`has`/`should`/`can` style prefix, or a function whose name doesn't say what it returns or
  does. → A precise name.
- **[nit]** A comment that restates what the code does. → Simplify the code and drop it; keep
  comments for why.
- **[must]** A comment, TODO or doc that this PR makes wrong. → Update or remove it.

## Docs

Tests are angle F's (`testing-checklist.md`), not this checklist's.

- **[must]** A change to how something is built, configured, run or used, with no update to the
  README/docs that describe it, when the repo keeps such docs. → Update them in this PR.

## Dependencies and config (only when the diff touches manifests, lockfiles, CI, env or config files)

- **[must]** A new or upgraded dependency whose declared range conflicts with what the repo pins:
  the runtime version (engines, CI matrix), peer dependencies, or another package's requirement.
  Quote both. → A compatible version.
- **[must]** A new config key, env var or feature flag added in one place the repo keeps them
  (`.env.example`, a config schema, per-environment files, deploy manifests) but not the others,
  or read without a default where its siblings have one. → Add it everywhere, with the same default.
- **[must]** Behavior that silently differs by environment: a debug branch, hard-coded local URL or
  test credential that would ship to production, or an environment check done by hand where the
  repo has a config layer. → The config layer.
- **[nit]** A new dependency for something the repo, the standard library or an installed package
  already does. Name it. → Use that.

## API contracts (only when the diff adds or changes an endpoint, event or public type)

- **[must]** A new or changed endpoint, event or public type whose naming, status codes, error shape
  or pagination differ from its siblings, or whose spec (OpenAPI, GraphQL schema, typed client)
  the PR doesn't update. Name a sibling. → Match it; update the spec.

## Accessibility (only when the diff touches UI markup or components)

- **[must]** An interactive element that a keyboard or screen reader can't use: a click handler on
  a `div`/`span` without role, focusability and key handling; an image without `alt`; a form
  control without a label; an icon-only button without an accessible name. → The native element,
  or the label.
- **[must]** A dialog, menu or route change that doesn't move or trap focus where the repo's
  existing components do. → The repo's component, or its focus handling.
- **[nit]** State conveyed by color alone, or a positive `tabindex`. → A text or icon cue; the
  natural order.

## Internationalization (only where the repo translates its UI)

- **[must]** A user-visible string written inline where the surrounding code uses translation keys.
  → A key in the repo's message files.
- **[nit]** A sentence built by concatenating translated pieces, or a date, number or currency
  formatted by hand where a locale-aware helper exists. → One message with placeholders; the helper.

## Consistency

- **[nit]** A new pattern where the repo already has an established one for the same job (data
  fetching, error display, file layout, naming). Name an existing example. → Follow it.

Sources: Google Engineering Practices, "What to look for in a code review"; Martin Fowler's code
smell catalog (Refactoring, 2nd ed.; refactoring.guru/refactoring/smells); SonarSource Cognitive
Complexity (default threshold 15) and nesting-depth (default 3) rules; WCAG 2.2 (accessibility).
