# Security and performance checklist (angle D)

Language- and framework-neutral. The repo's own written rules override any advice here.
Apply it to every line the PR adds or changes. Every finding is scored like a bug, so each needs
evidence, not a pattern match:

- **Security:** the path from where the untrusted value enters (request, URL, header, file, env a
  user controls, third-party response) to where it's used, and why nothing on the way already
  stops it. Grep for the repo's own guard (middleware, validator, escaping helper, ORM binding,
  policy) before flagging; if it exists and covers this path, there is no finding.
- **Performance:** the loop or hot path and what grows with input (rows, items, requests), and why
  the size isn't already bounded (pagination, a fixed list, a cache in front).

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
- **CSRF.** A state-changing endpoint reachable by GET, or excluded from the framework's CSRF
  protection, with cookie-based auth. → POST/PUT/DELETE behind the existing protection.
- **Secrets.** A credential, token, private key or connection string in code, config, tests or logs;
  a secret or PII written to logs, errors or client responses. → Env/secret store; redact.
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

- **N+1 queries.** A query, API call or lazy-loaded relation inside a loop over rows or items. →
  One batched query, eager loading, or a lookup map built before the loop.
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

Sources: OWASP Top 10 (2021) and the OWASP Cheat Sheet Series; the `code-review` skill of
Anthropic's `engineering` plugin (its security and performance dimensions).
