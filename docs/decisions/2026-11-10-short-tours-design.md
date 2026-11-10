# The short tours

Decision D356, after the first tour ([A tour the person does with their own
hands](2026-11-10-guided-tour-design.md)).

## What they are for

The first tour stops at the basics on purpose: a long one is abandoned. The
rest of the application is offered as short tours, each a few minutes, taken
from Preferences → Tours whenever a person wants, and taken again.

## Do, or only show

Where something can be done in a minute on data the tour can make itself, the
person does it: a table read as a chart, a structure and documents; a
pipeline saving a table as a CSV in their own folder. Where doing it needs
what a tour cannot bring — metrics that take minutes to arrive, an agent
running on another machine, a provider's key — the tour only shows where
things are and goes on with Next.

Dashboards were first to be joined with starting a PostgreSQL here and
switching its metrics on. Rejected: the first points arrive a poll or two
later, and dashboards are made for agents reporting from elsewhere; a
connection's own metrics are an addition, and are shown as one.

Starting a service is not a short tour: it closes the first one, Redis ringed
in the catalog of types and not started.

## A practice database each time

A short tour that works on data makes a SQLite file with the lab (D263)
before its first chapter and deletes it when it ends. A shared practice
database kept until removed from Preferences was the alternative; a database
made and taken away each time repeats the first tour's cycle and leaves
nothing behind. Deleting the file needs the server: a connection is now
deleted with its file on request, refused while another of the owner's
connections opens it.

## Kept on the account

The tours taken are a list on the preferences row, added to one at a time, as
the welcome's own is a flag there.
