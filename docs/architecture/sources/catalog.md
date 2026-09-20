# What a catalog shows

What a node says about itself, how a catalog is searched, and a source whose
names are a catalog only once they are grouped. What every source must answer is
in [contract.md](contract.md); how the tree behaves on screen is in
[../workspace.md](../workspace.md).

Decisions here: D75, D76, D91.

## D75. A node describes itself, and that is neither a viewer nor an action

A representation says what is inside a document ([D47](content.md)); a relation
model says what shape something tabular has; an action does something and reports
a message ([D9](actions.md)). None answers "what is this" — how big, since when,
what it may be opened as, what its format states — and a folder, a recording and
an opaque binary have no answer at all without a fourth capability.

- `SupportsNodeSummary` answers `NodeSummary` for one node id at
  `GET /connectors/{id}/node-summary`. Reading is enough: everything in it is
  already visible to somebody who may list the level the node sits in.
- It is deliberately not `SupportsRelationModel` with more fields. That model is
  the shape of something tabular, and half of it — schema, owner, persistence,
  constraints — is vocabulary a folder does not have. A capability answers one
  question about one kind of thing.
- `CatalogNode.summarizable` says which nodes have one, the way `describable`
  says which answer a relation model ([D51](content.md)). A client that worked
  it out from the kind would be deciding what a source can answer.
- The facts every node has are flat and shared: size, the times the platform
  states, the POSIX mode, and `representations` — the same ordered list the
  catalog gives, so "what can this be opened as" is computed once.
- What a format states is a discriminated union, `NodeContents`, for the reason
  `DatasetInfo` is one: a screen rendering "name: value" pairs written by the
  source shows text nobody can check. Two of its members are `DatasetInfo`'s
  own, because a Parquet file states here exactly what it states there.
- **A time the platform does not keep is absent.** A creation time is reported
  only where `st_birthtime` exists; Linux's `st_ctime` is when the inode last
  changed, and filling the field with it would be a plausible lie.
- **Every count has a ceiling and says when it hit one.** A file over 32 MB is
  not read through, and a folder is counted no further than the 2000 entries its
  own listing refuses to go past — the same number in both messages. `lines`
  absent with `not_counted` set is the shape, never a zero.
- **A misleading suffix reaches the reader rather than the log.** Bytes that are
  not the format their name promises leave `contents` empty and put the reader's
  own refusal in `notice`, which is D47's known deviation finally being said out
  loud. An `OSError` is not passed on: its text carries the path.
- **A relational source answers it too, and the answer is not the relation
  model.** The model is a table column by column and has a screen of its own; the
  summary says what the thing is — how it is stored, who owns it, how many
  columns, indexes and constraints it has, how big it is on disk, and how
  recently the server measured it. `RelationContents` is built from the model
  that screen already asks for, so nine columns are counted by the query that
  would list them. Its `relation_kind` is narrower than the node's kind on
  purpose: a materialized view is a view to somebody walking the catalog and a
  stored table to somebody asking how it works.
- **A relation's "since when" is when it was last measured.** PostgreSQL keeps
  neither a creation time nor a time of last write, so those fields stay absent
  rather than being filled with something plausible, and the one statement
  written for this capability reads `pg_stat_all_tables` for the last analyse
  and the last vacuum, whether a person asked for them or autovacuum did. A
  view has no entry there at all and states neither.
- Nothing new is read to answer this. The archive's central directory, the
  workbook's sheet list, the Parquet footer, the media header and the image
  header are the readers this source already had; the one pass written for the
  summary counts the lines, the longest line and the line endings of a text
  file, which nothing else needed.

Known deviations:

- **Only relations answer it on a PostgreSQL server.** A schema is not marked
  summarizable, and neither is a report. A schema's summary would be a count of
  what it holds, which is a different question from "what is this thing", and
  nobody has asked it yet.
- **An entry inside an archive states only what the archive states.** Counting
  its lines would cost expanding it to a temporary file of up to 32 MB
  ([D53](content.md)), and this question is not worth one.
- **A folder is counted one level deep.** A recursive size is a walk of the
  whole tree, which is a job rather than a request.
- **A summary is not cached and not invalidated.** It is a stat and a bounded
  read, and a file source has not opted into [D31](connecting.md).
- **It is opened from the catalog and nowhere else.** A rows tab offers
  Structure and no Details, because the node it shows is in the catalog,
  which is where the question is asked and where the nodes that have no
  rows are. It is a line of the catalog's one menu, beside Copy and Cut
  ([D74](actions.md)).

Spec: [A node describes itself](../../decisions/2026-09-02-node-summary-design.md)

## D76. A search is a read of the catalog, and the words are the filter's

The catalog's filter narrows what is already on screen, which is the wrong tool
for a name somebody remembers in a place they do not.

- `SupportsNodeSearch.search_nodes` answers `NodeSearchResult` at
  `GET /connectors/{id}/catalog/search`, and what comes back is
  `CatalogNode`s — the same nodes a listing gives, built by the same builder.
  A found row therefore has the icon, the caption, the viewers and the actions
  its level would have given it, and nothing on the screen needs a second kind
  of row.
- **The words are the ones already typed.** The filter narrows this level; the
  button beside it asks the source for what is not on it — one input, two
  questions, and no second field to fill in. While results are shown the list
  is not a level: it says so, offers the way back, and every row on it behaves
  as it would at home.
- **The text is matched, never compiled.** A case-insensitive substring of a
  name, and no pattern language at all — [D2c](contract.md#d2c-a-query-is-never-built-from-client-strings)'s
  rule stated for the one input this capability takes. A `*` is a character in
  a name.
- **A match says where it was found, twice over**: `parent_id`, the source's own
  opaque id, which is what a client sends back to stand there; and `location`,
  the same place as the source words it, because a client that composed one
  from an id would be reading it apart ([D21](contract.md#d21-the-source-answers-where-a-node-lives)).
  The root is the empty string — it has no name of its own.
- **Breadth first, and bounded three ways.** What is near is found first, so a
  ceiling cuts the far end rather than a random branch. At most the matches
  asked for (100 by default, 500 at most), 100,000 entries looked at and 24
  levels deep; a walk that hit one says `complete: false` and why. "Nothing
  else matched" and "I stopped looking" are different answers, and only the
  second means type more words.
- **A link is listed and never walked into.** An alias can duplicate a whole
  tree into the results or point at its own parent, and a search is exactly
  where a loop would be met. It is the archive walk's refusal, for its reason.
- **Only a match is described.** The name decides first, and a node is built
  only for one that matched: describing every entry of a hundred thousand would
  cost a stat and a listing each to answer what a string comparison answers.
- **A folder that cannot be read is skipped, not fatal.** The rest of the tree
  is still an answer, exactly as a listing leaves out what it cannot stat.
- **Which sources can be searched is read off a code.** `Capability` gained
  `code`, a closed set, beside the title it already had: a title is written to
  be read and may be reworded, and a screen that switched on one would be
  branching on prose. It is still derived by `issubclass` in `capabilities_of`,
  so nothing is listed by hand ([D13](contract.md#d13-a-source-type-describes-itself)).
- **Looking inside the files is the same search held down.** `SearchesContents`
  is its own capability, code and route,
  `GET /connectors/{id}/catalog/search-contents`: a different promise at a
  different price, since matching a name is milliseconds and reading every file
  below a folder is minutes. A source that lists names and cannot read them
  answers 501, and the client never offers the gesture. Same walk, same bounds,
  same nodes — only what decides a match changes.
- **The gesture is Shift, and it explains itself once.** The same words in the
  same field and the same button, held: a second field would be a second thing
  to fill in for one question. The first time, a confirmation says what it will
  cost and offers to stop asking; the answer is remembered in this browser,
  because it is about a habit rather than about the data. Ticking the box and
  then cancelling remembers nothing — that is not an agreement.
- **A match carries the line it was found on.** `NodeMatch.excerpt`, cut to 200
  characters, becomes what the row says about itself in place of a file size: a
  search inside files that showed neither the line nor the words would be a
  list of names. A name search leaves it empty, because there the name is
  already the row.
- **Reading is bounded on top of the walk's bounds.** A file over 8 MB is
  skipped, one that looks binary is skipped, and the whole search stops after
  256 MB read however many files that took. Skipped files are counted and said:
  "no matches" must not stand for "a picture and a dump were never opened".

Known deviations:

- **Only the file source searches.** PostgreSQL answers 501 to both routes;
  relation names across schemas are one `ILIKE` away and are a later slice.
- **Nothing inside a container is found.** A workbook's sheets and an archive's
  entries are nodes ([D51](content.md), [D53](content.md)), and the walk does
  not open files.
- **A search inside files answers with files, not with lines.** One line per
  file, the first that matched, so the answer stays a list of catalog nodes and
  a found row still opens the way any row does. Every hit in a file, the way a
  code editor lists them, is a different result and a later slice.
- **A search is not paged.** Past the ceiling the answer is the first N and a
  notice; there is no cursor.
- **Anything that changes the level ends the search**, an action included: the
  results came from a walk that is now stale, and re-running it silently would
  be inventing a second reload nobody asked for.

Spec: [Searching the catalog by name](../../decisions/2026-09-02-catalog-search-design.md)

## D91. A key space is a catalog, grouped by the separator its names already use

Redis has no schemas and no tables — a flat set of names, which by universal
convention are written with colons: `session:42:token`, `cache:user:7`. Every
tool that shows a key space shows that convention as a tree, because it is the
structure the names were given when they were chosen.

- **The root is the server's databases, and inside one the catalog groups by
  `:`.** A database lists the first segment of every key as a branch, and
  opening one lists the next. Not configurable: a source type whose tree shape
  is an option is a type with two behaviours to explain, and every Redis
  convention there is uses this one.
- **A database is a grouping, not a wall.** The number written into the
  connection says which one the catalog opens on; the rest are beside it in
  the same control a database's schemas are chosen in. `DatabaseNode` is a
  kind of its own — a schema is a namespace inside one database and several
  can be read together, while these share nothing but the port — and it says
  how many keys it holds, from one `INFO` rather than a `DBSIZE` apiece.
- **Which grouping a catalog opens on is the source's answer.** `preferred`
  marks it, because only the source has read the connection. Everything else
  keeps the client's rule: every non-system grouping while there are few, the
  first while there are many.
- **Both of those are only for a connection nobody has an opinion about yet.**
  A choice made in the grouping control is remembered by the browser, keyed by
  server and connection the way a grid remembers its columns, and the catalog
  opens on it next time — turning a schema off and finding it back after a
  reload is the application overruling the person. Nothing chosen and
  everything turned off are different answers, and only the second is
  remembered as such; a remembered choice whose groupings have all gone falls
  back to the rule above.
- **How many databases there are is asked of the server**, since it is a
  setting; a server that refuses to say — as managed ones do — gets the
  sixteen every client assumes.
- **A key is a kind of its own.** `KeyNode` carries a Redis data type, an
  expiry and a length; reusing `table` would give one kind two meanings — what
  D2a says the old application did — and would offer every action that names a
  table on a key. The namespace above it is a `directory`, because a container
  of nodes with nothing else to say about itself is what a namespace is.
- **Every id carries its database, and a letter says which kind it is**:
  `d3`, `f3:cache:`, `k3:cache:user`. The database, because a key of the same
  name in two of them would otherwise be the same string; the letter, because
  a key may itself be called `user:`, and without it a listing of that key and
  a listing of the folder above it would be the same request. Ids are read
  strictly — a string that is nearly one of ours is refused rather than nearly
  understood — and nothing but `keyspace.py` takes one apart (D21).
- **Nothing ever runs `KEYS`.** It blocks the server for the length of its own
  scan. Everything is `SCAN`, which exists so that a client cannot do that, and
  a listing stops at a ceiling: a key space of ten million names has no useful
  tree, and a page that tried to draw one would fail slowly rather than
  quickly.
- **What a key holds is read as rows, and the shape follows the type.** A hash
  is fields and values, a list is positions and values, a sorted set is members
  and scores. One table per type rather than a chain of branches, so a type
  that gains a reader is a line.
- **Nothing sorts and nothing filters.** Redis has no index over values, so a
  column that offered either would be offering something this source would
  have to fake by reading everything.
- **What people do to a key by hand**: write one, take it away, give it a
  deadline, take the deadline off. Writing covers changing a value: a name
  already in use is refused unless the form says to replace it, which makes
  "write this" one action rather than a create and an update differing only in
  their refusals. Replacing removes what is there first, so a string may become a
  hash.
- **Writing is one action per type of key.** Redis has six, each written with a
  different command and asking for a different thing. One action with a type to
  pick would be one form whose only box means six things depending on a select
  above it, and whose description could describe at most one. The six share
  everything else through one base class, so a seventh type is a class with one
  method in it.
- **What a key holds is edited element by element**, through the same contract
  every relation uses (D25, D26): a field of a hash, a position in a list, the
  score of a member. The actions write a whole key, which is how one is made;
  this is how one is corrected, and a person looking at a page should be able
  to type into it rather than rewrite the key around the cell they meant.
- **What stands in for a row version is a fingerprint of what was read.**
  Redis has no `xmin` and no compare-and-set for a field, so the row handle
  carries a digest of the values the page showed, and an edit whose element no
  longer holds them is refused rather than applied. Optimism with a re-read:
  honest about being a race the server does not arbitrate, and still better
  than overwriting what somebody has just put there.
- **What each type admits is the writer's to say, and the page says the same.**
  A string offers its value and no rows to add — there is one, and removing it
  is removing the key; a list offers its values but not its positions, because
  where an element is is not something it holds; a stream offers nothing,
  because an entry is an event that was written once. The refusals are one
  table, read both by the page that offers the edit and by the write that
  would refuse it, so the two cannot say different things.
- **A key is made where the catalog is standing.** The name typed into the
  form is added to the prefix of the place, so `one` written in `cache:` is
  `cache:one`. Worked out by the source, which is the only party that may take
  an id apart (D21).
- **A destructive action may word its own question.** Everything destructive
  until now removed what it named, so the client wrote "are you sure you want
  to delete this" itself. Setting an expiry is destructive and is not a
  deletion, and only the action knows the difference.
- **The catalog is expanded where it stands, not walked.** A source declares
  which of the two it wants — `catalog_shape` is a `Literal`, read off the
  type rather than branched on by name — and a key space says `tree`, because
  it is bounded and its shape is already in the names. A tree shows no path
  and no search, because both are properties of a level; it keeps the control
  that picks a grouping, because a grouping is where the tree is rooted. The
  actions menu is fed from the one selected node instead of from a set of
  ticks.
- **A click is on the whole row.** A branch opens and closes by its name, and
  a leaf opens in a tab; reaching for the arrow beside the name was a
  ten-pixel target for the commonest thing anybody does to a tree. Every click
  also selects and the selection stays — the menu of actions acts on it, and a
  menu whose subject clears itself under the pointer is worse than one with no
  subject at all. The selected row is marked across its whole width, arrow and
  indent included.
- **Opening a branch is asked of the tree, never marked from outside.** A
  branch loads its children as it opens, so the component that opens it is the
  one that asks for them; adding a key to the set of open branches marks it
  open and asks for nothing, and it stays shut with its arrow pointing the
  wrong way.
- **A tree stops at the nodes.** Expanding a branch asks the catalog for its
  children; a leaf is opened in a tab, exactly as it is in a list. Showing the
  first rows of a key inside the tree made one branch mean two different
  things depending on how far it was opened, and gave the same value two
  places to be read in.
- **One grouping at a time in a tree.** Several schemas listed together are
  one list with a column saying where each row came from; several key spaces
  expanded together would be one tree with no such column, and nothing joins
  them.

Known deviations:

- **A large key space is listed as far as the ceiling and no further**, and the
  listing does not say that it stopped. What is beyond it is reached by naming
  a narrower prefix, which the catalog offers no way to type.
- **A collection is written from lines of text**, one member or one
  `name=value` per line, rather than from a repeating group of fields. It is
  what the form vocabulary has, and it is enough for a key made by hand; a
  hash of forty fields arrives from whatever writes it.
- **A name in use is checked and then written to, in two commands.** Only
  `SET` has a "if it is not there" of its own, so the five other types would
  each need a transaction to say the same thing. The gap between the two is a
  race nobody writing keys by hand loses.
- **An element of a list cannot be removed.** Redis removes by value or by
  trimming the ends, so removing the third of five means writing a sentinel
  over it and then removing that — two commands and a value nobody asked for.
  The page says so instead.
- **A hash and a set are paged in this process.** Both are read whole and then
  sliced, so a hash of a million fields is a million fields in memory. A list
  and a sorted set page in the server, because those two carry an order.
- **A value is decoded with replacement.** Redis holds bytes and says nothing
  about what they mean, so a key holding a JPEG shows as replacement
  characters rather than being refused.
- **There is no query console.** Redis has commands, not statements, and a
  console that accepted them would be a shell on somebody's server (D65).
- **Nothing watches.** A key that expires while its page is open stays on the
  page until it is read again.
- **A tree is not filtered and not searched.** Both belong to a level, and
  neither has been given a meaning for a tree yet; what is on screen is the
  whole of a bounded key space.
- **A tree re-reads whole after an action.** Which branches changed is still
  the server's answer, but keeping a map of what is open in step with it costs
  more than reading a bounded catalog again — so what was open closes.
- **A database that is not on the server is refused by the server.** The id
  grammar accepts three digits and the connection to a database out of range
  fails on connect, rather than being checked against a count this application
  holds.

Spec: [A key space, walked and written](../../decisions/2026-09-03-redis-keyspace-design.md)
