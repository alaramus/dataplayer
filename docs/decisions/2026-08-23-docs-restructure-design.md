# Restructuring the project documentation

Date: 2026-08-23

## Problem

`AGENTS.md` has grown to 1224 lines and 74 KB. It is imported from `CLAUDE.md`,
so it is loaded in full into the context of every session. Together with
`ENGINEERING.md` (235 lines, 12 KB) that is ~22k tokens before the first line
of code, of which usually a tenth is relevant.

The second problem is the cost of maintenance. One iteration edits
`Current state`, `Decisions`, `Known deviations` and `What comes next`, that is
four places, and they drift apart. The run commands are written down three
times: in `AGENTS.md`, in `development.md` and in `README.md`.

The two problems give two requirements: a small core that is always loaded, and
one place per area that an iteration writes to.

## Decisions

### R1. The core is always loaded, the rest on demand

`AGENTS.md` is cut down to ~180 lines: what the project is, a reading map, what
already works, a decision index, commands, traps, working rules, what comes
next. Everything else moves to files the agent opens itself.

The traps stay in the core even though they are 55 lines. They cannot be
derived from the code, and one cannot count on the agent opening a traps file
**before** it walks into a trap. The commands stay for the same reason: an
agent that needs to run the tests either reads an extra file or makes up the
command itself.

The decision index is one line per decision with a file name. It is needed so
that the agent knows a decision exists before opening the file; without the
index, selective reading turns into not knowing.

`ENGINEERING.md` does not change and stays loaded in full. It is always
normative, whatever area the task touches, so "I will read it when I need it"
does not apply to it.

### R2. The rest is split by area, not by kind

```
docs/architecture/adapters.md    D1, D2, D2a, D2b, D2c, D2d, D8, D9, D10, D13, D15, D16, D17
docs/architecture/backend.md     D3, D4, D5, app/ structure, API list
docs/architecture/frontend.md    D6, D7, D11
docs/architecture/workspace.md   D12, D14
```

The boundary is drawn by work, not by topic. Someone adding a data source
reads one file in full rather than collecting thirteen ADRs one by one.
Splitting by kind (`decisions.md`, `deviations.md`, `state.md`) was rejected:
it is a mechanical move of today's sections, after which an iteration still
edits three files, so the second problem is not fixed.

Each area file has three parts: what is here today, including its own piece of
the directory tree; decisions; known deviations. A deviation sits **under the
decision it departs from**, not in a separate list. The 224-line list ceases
to exist, and an iteration edits one file.

The cost: the question "all deviations of the project" requires opening four
files. The question "what is wrong in the adapters" gets asked; the first one
does not.

The D numbering is kept as is, with gaps and suffixes. 17 specs and commit
messages refer to it; renumbering would break the references for the sake of
cosmetics.

### R3. Narrative is replaced by enumeration, retrospectives are removed

The `Current state` (199 lines) and `What comes next` (105 lines) sections are
written in expansive prose and retell what the specs already say.

The prose is replaced by dense statement: one fact per line, no figures of
speech. The former literary style was not a requirement — it arose on its own
while everything lived in one file.

Paragraphs of the kind "what this iteration gave and what to carry forward" are
removed: they duplicate the endings of their specs and go stale first. Their
place is taken by `docs/superpowers/specs/README.md` — an index of finished
subprojects, one line each with a link to the spec.

### R4. Commands live in one place

`development.md` is deleted. The commands stay in the core of `AGENTS.md`.
`README.md` is cut down to "what this is, stack, first run, where to read
next" — it is addressed to a person arriving from GitHub.

### R5. The restructuring leaves a check behind

`scripts/check-docs.sh` asserts three things:

1. Every relative link in tracked `.md` files leads to an existing file.
2. Every decision in the index in `AGENTS.md` appears as a heading in exactly
   one file of `docs/architecture/`, and conversely — there is no orphan
   decision.
3. `AGENTS.md` does not exceed 16 KB.

The third assertion is what the whole thing is for. Without a number the file
will grow again within two or three iterations.

The check is added as a row in the "What holds it up" table in
`ENGINEERING.md`. That is the only change to that file.

Each of the three assertions is verified by breaking it on purpose and
observing red — as `ENGINEERING.md` requires of any contract declared working.

## What is deleted rather than moved

The list is given so that a deletion can be disputed in advance.

- Retrospective paragraphs in `What comes next` (~60 lines): "what the
  subproject settled and what to carry into 7". They duplicate the endings of
  the specs.
- Explanations by way of the old application inside decisions where the same
  thing is written in more detail in the decision's spec. One sentence of
  reason stays, the analysis does not.
- Overlaps between `Current state` and the decision sections: the same property
  of the product described in both.
- `development.md` in full: the commands move to the core, "where things are" —
  to the core, the rest duplicates `README.md`.

## Order of execution

Area by area, each its own commit, because the content is rewritten rather
than moved, and the diff has to be read by eye.

1. `docs/architecture/adapters.md`
2. `docs/architecture/backend.md`
3. `docs/architecture/frontend.md`
4. `docs/architecture/workspace.md`
5. `AGENTS.md` — cut down to the core
6. `README.md`, deletion of `development.md`
7. `docs/superpowers/specs/README.md`
8. `scripts/check-docs.sh`, the row in `ENGINEERING.md`, verification by three
   breakages

## Verifying the result

- `bash scripts/check-docs.sh` — clean.
- Three deliberate breakages give red, each for its own assertion.
- `wc -c AGENTS.md` — less than 16384.
- None of the decisions D1..D17 is lost: the core's index is checked against
  the area files by the same check.
- `git show :AGENTS.md | file -` before the commit — the file has not been
  rewritten in CRLF (a known trap of the project: once this turned an edit into
  a 597-line diff).

## What stays outside

- The 17 existing specs are not rewritten. They refer to `AGENTS.md` as a file,
  not to anchors, so the links survive the restructuring.
- The plans in `docs/superpowers/plans/` are not touched: they are records of
  work done.
- No automatic generation of the directory tree. The tree is written by hand,
  as it is now; the value is in the comments on the lines, not in the list of
  files.
