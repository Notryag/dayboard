# Current Documentation

These three documents are the canonical description of the implemented product:

- [architecture.md](./architecture.md): system boundaries, infrastructure, persistence, frontend,
  and deployment shape.
- [product-model.md](./product-model.md): user-facing concepts and scheduling semantics.
- [run-lifecycle.md](./run-lifecycle.md): queued execution, Redis Stream/SSE delivery, persistence,
  recovery, clarification, cancellation, and usage.

Update these files in the same change whenever implementation alters their contracts. Do not place
historical rationale or milestone checklists here; use ADRs and the archive respectively.
