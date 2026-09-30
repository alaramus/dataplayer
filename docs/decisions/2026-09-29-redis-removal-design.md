# Removing Redis table overlays and declared references

**Date:** 2026-09-29  
**Decision:** D195

## Decision

Redis remains a keyspace grouped by the colons in key names (D91). Remove the
application-owned table overlay over Redis folders (D170), Redis tables as
endpoints of declared references (D172), and the editing path for those tables
(D173).

Keep Redis keys, folders and databases available to the existing Copy and
Paste flow and CSV export (D171). The adapter's relation model remains for the
column names and row shape needed by CSV; it does not make Redis eligible for
the Relationships graph or declared references.

Declared references remain a general application feature (D106–D108). A source
can be an endpoint only when it implements row lookup and node-path contracts;
the `declared_references` capability gates the structure panel's section. The
Relationships graph has its own capability, present only when the adapter
provides both relation models and node paths. This keeps graph availability
separate from the metadata a source may need for CSV.

Remove the declared-table storage column, its API, adapter protocol and Redis
implementation. The migration that added the column is removed from the fresh
schema history; no data-cleanup migration replaces it.

## Why

Redis has no tables or relationships. The overlay asked people to maintain a
second schema in DataPlayer and made a folder look like a relational source.
That brought table editing and reference navigation without changing what
Redis itself can describe. The supported raw-key workflow already has the
useful transfer: copy nodes to a file or SSH source as CSV, or export their
rows directly.

CSV still needs stable column names for each Redis key type and the key-listing
shape for folders and databases. Retaining `SupportsRelationModel` for that
purpose preserves the established transfer while the distinct graph and
reference capabilities stay unavailable.

## Consequences

- Redis no longer offers **Describe as table**, Redis table rows, Redis table
  editing, or Redis endpoints for **Declared references**.
- The general declared-reference APIs and UI remain available for supported
  sources; their structure section is gated by `declared_references`.
- Redis key, folder and database copy/paste and CSV export remain.
- The Relationships graph capability no longer follows from relation-model
  support alone; adapters must also provide node paths.
- The old D170, D172 and D173 specs remain frozen history. This decision is the
  live contract.
