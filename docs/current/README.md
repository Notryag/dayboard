# Current Documentation

These documents are the canonical description of the implemented product:

- [architecture.md](./architecture.md): system boundaries, infrastructure, persistence, frontend,
  and deployment shape.
- [module-map.md](./module-map.md): code placement, dependency permissions, public module contracts,
  transaction ownership, and cross-module invariants.
- [product-model.md](./product-model.md): user-facing concepts and scheduling semantics.
- [identity-model.md](./identity-model.md): authenticated user ownership, isolation, and HTTP/Worker
  identity boundaries.
- [run-lifecycle.md](./run-lifecycle.md): queued execution, Redis Stream/SSE delivery, persistence,
  recovery, clarification, cancellation, and usage.
- [time-protocol.md](./time-protocol.md): Beijing local model protocol, UTC persistence, artifact
  isolation, and row-version concurrency.

Update these files in the same change whenever implementation alters their contracts. Do not place
historical rationale or milestone checklists here; use ADRs and the archive respectively.

For backend implementation, read `architecture.md` and then `module-map.md`. For Run, stream, or
clarification changes, continue with `run-lifecycle.md`. Do not read every current document when the
task does not cross those boundaries.
