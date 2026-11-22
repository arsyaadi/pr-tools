# Security and performance checklist (angles D and E)

Language- and framework-neutral. The repo's own written rules override any advice here.
Apply it to every line the PR adds or changes. Every finding is scored like a bug, so each needs
evidence, not a pattern match:

- **Security:** start at the trust boundary, where data an attacker controls enters (request body,
  URL, headers, cookies, uploaded files, webhooks, third-party responses, another tenant's data),
  and follow it through the actual execution path to where it's used, saying why nothing on the
  way already stops it. Values the client sends (price, role, user id, `isAdmin`) are untrusted
  even when the UI hides them. A suspicious keyword is where tracing starts, not a finding. Grep
  for the repo's own guard (middleware, validator, escaping helper, ORM binding, policy) before
  flagging; if it exists and covers this path, there is no finding.
- **Performance:** the loop or hot path and what grows with input (rows, items, requests, uptime),
  and why the size isn't already bounded (pagination, a fixed list, a cache in front).

A finding needs the line, the item, the evidence above and a concrete one-line fix. Skip what the
framework already does by default (auto-escaping templates, parameterized ORM calls, built-in CSRF
tokens) unless the PR turns it off or goes around it.

## Security

- **Injection.** Untrusted input concatenated or interpolated into SQL, NoSQL filters, shell
  commands, `eval`, template source, LDAP, XPath or regexes. → Bound parameters, an argument array,
  or a whitelist.
- **XSS.** Untrusted input rendered as HTML (`innerHTML`, `v-html`, `dangerouslySetInnerHTML`,
  `|safe`, raw template output) or into a URL/`href` without a scheme check. → Text binding, or the
  repo's sanitizer.
- **Broken access control.** A new route, handler, query or mutation with no authn/authz check where
  its siblings have one; an object fetched by an id from the request without checking the caller
  owns it (IDOR); a role or permission check done only on the client. → The guard its siblings use.
- **Authentication bypass.** A path into a protected handler that skips the check: an early return
  or branch before it, a route, HTTP method or content type the guard doesn't cover, a flag or
  header that turns it off, a token or session accepted without checking signature, expiry or
  audience. → Put the check where every path passes through it.
- **Privilege escalation.** A role, permission, tenant or owner value the caller can set (body,
  query, claims they control), or a query missing the tenant or owner scope its siblings apply. →
  Take it from the server-side session; add the scope.
- **Authorization race.** A permission, balance, quota or ownership check and the action it guards
  done in separate steps without a lock or conditional write, so two concurrent requests both
  pass. Name the order. → Check and act in one atomic statement, or under a lock.
- **Rate limits and resource exhaustion.** A new public or unauthenticated endpoint that does
  expensive work (email, SMS, hashing, external calls, large queries) or checks a guessable secret
  (login, OTP, reset token) with no rate limit where its siblings have one; an unbounded upload,
  body or batch size; a regex with nested quantifiers run on input (ReDoS). → The repo's limiter;
  a size cap; a linear regex.
- **CORS.** The request's origin reflected, or a wildcard, together with credentials; an allow-list
  matched by substring or suffix. → An exact allow-list.
- **CSRF.** A state-changing endpoint reachable by GET, or excluded from the framework's CSRF
  protection, with cookie-based auth. → POST/PUT/DELETE behind the existing protection.
- **Secrets.** A credential, token, private key or connection string in code, config, tests or logs;
  a secret, auth header, session id, whole request body or PII written to logs, errors, analytics
  or client responses. → Env/secret store; redact.
- **File permissions.** A file or directory created world-readable or world-writable when it holds
  secrets or code (`0777`, `0666`), or a temp file with a predictable name in a shared directory. →
  `0600`/`0700`, the platform's secure temp API.
- **Insecure deserialization.** Untrusted data into `pickle`, `yaml.load`, `unserialize`,
  `ObjectInputStream`, `Marshal`, or a JSON parser configured to instantiate types. → A safe loader
  and a schema.
- **Path traversal.** A file path built from untrusted input without normalizing and checking it
  stays under the intended root. → Resolve, then check the prefix; or map ids to paths.
- **SSRF and open redirect.** A server-side request, or a redirect, to a URL taken from input
  without an allow-list. → Allow-list hosts; relative redirects only.
- **Weak crypto and randomness.** MD5/SHA1 for passwords or signatures, a hand-rolled cipher, ECB,
  a fixed IV/salt, `Math.random`/`rand()` for tokens or ids that must be unguessable, a disabled TLS
  check. → The platform's password hash / CSPRNG / defaults.
- **Mass assignment.** A whole request body passed into a model create/update. → An explicit field
  list.

## Performance

- **N+1 queries and missing batching.** A query, API call or lazy-loaded relation inside a loop
  over rows or items, or one insert, update or request per item where a bulk API exists. → One
  batched query or bulk call, eager loading, or a lookup map built before the loop.
- **Unbounded work.** A query, list endpoint or loop with no limit/pagination over data that grows
  with usage; reading a whole table, file or response into memory. → Paginate, stream or cap it.
- **Quadratic hot path.** A nested loop, `includes`/`indexOf`/`find` inside a loop, or repeated
  array copying, over input that can be large. → A Set/Map lookup, or one pass.
- **Missing index.** A new query filters, joins or sorts on a column the schema/migrations show no
  index for, on a table that grows. Name the migration you checked. → Add the index in this PR's
  migration.
- **Repeated work.** The same expensive call (query, fetch, parse, regex compile) made more than
  once per request or render with the same inputs. → Compute once and reuse.
- **Resource leaks.** A connection, file handle, stream, subscription, timer or listener opened
  without a close/cleanup on every path, including errors and unmount. → `finally`, `with`/`using`,
  or the cleanup hook.
- **Blocking the hot path.** Sync I/O, a sleep, or a CPU-heavy loop on a request handler, event
  loop or UI thread. → Async, a background job, or a worker.
- **Sequential awaits.** Independent async calls awaited one after another in a request path. →
  Run them concurrently.
- **Connection pool exhaustion.** A connection or client acquired per item or request and not
  released on every path, a new pool per request, or a transaction held open across an external
  call or a wait. → The shared pool; release in `finally`; the external call outside the
  transaction.
- **Unnecessary locks.** `SELECT … FOR UPDATE`, a table lock, or a long transaction that holds locks
  over more rows than the write needs or during I/O. → Lock only those rows, only for the write.
- **Cache invalidation.** A write path that changes data a cache serves without invalidating or
  updating that cache (stale reads until expiry), or a cache key missing a dimension the result
  depends on (user, tenant, locale), which also leaks data between users. → Invalidate on write;
  complete the key.
- **Cache stampede.** A hot key with a fixed expiry and no lock, jitter or stale-while-revalidate,
  so many requests recompute the same expensive value at once. Only with evidence the key is hot.
  → Single-flight or a lock; jittered expiry.
- **Serialization and logging overhead.** Serializing or deep-cloning large objects per request or
  per item, logging inside a hot loop, or logging whole payloads. → Serialize once; log a summary
  outside the loop.
- **Memory growth in long-running processes.** A module-level map, array, cache or listener list in
  a worker or server that grows per job or request with no eviction or cleanup. → Bound it (LRU,
  TTL), or scope it to the job.

Sources: OWASP Top 10 (2021) and the OWASP Cheat Sheet Series; the `code-review` skill of
Anthropic's `engineering` plugin (its security and performance dimensions).
