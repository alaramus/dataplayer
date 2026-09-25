# Moving a file between connections

Date: 2026-09-25. Decision: D163. Extends D161 and D162.

A Cut selection is an intent until Paste runs. When its source and destination
are different connections, the application requires write access to both.
The destination stages and publishes each complete file, then the source is
checked for changes and asked to remove that file. If removal fails, the
published copy remains and the original remains; the response says so. A batch
may therefore have completed earlier files when a later one fails. Both
connection catalogs are refreshed after an attempt, and the clipboard is
cleared only when the move succeeds.

The same Paste command and conflict window serve Copy and Cut. For a
cross-connection Cut, a taken name can be resolved by keeping both files under
different names. Replace is withheld: two distinct connector records may
address the same underlying file, and replacing that file before deleting the
source could erase the newly published destination. Safe replacement needs a
cross-storage identity rule, which this slice does not have. Same-connection
Cut retains the source-owned action's existing choices.

The first move supports files only, with D161's count and byte ceilings.
Directory trees, an all-or-nothing batch, undo, and durable jobs are separate
work. An SSH file is still read and removed through its storage; no remote
shell command is involved.
