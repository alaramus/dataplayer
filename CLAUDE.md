# CLAUDE.md

Read [AGENTS.md](AGENTS.md). It is the canonical guide for this repository and
covers what the project is, the decisions behind the current code, the
commands, and the traps that are not visible from the source.

Do not duplicate that content here.

## Short version

DataPlayer is a rewrite of an older working application — backend at
`C:\Users\maxim\PycharmProjects\dbwebtool`, frontend at
`C:\Users\maxim\PycharmProjects\myquasar`. We port **ideas, not code**: read the
old sources to understand a problem, then design the new implementation from
scratch.

Everything in the repository is written in English, except the working notes in
`docs/superpowers/`.

The starting point was `fastapi/full-stack-fastapi-template`. It is not a
constraint — most of it has already been rewritten or removed.
