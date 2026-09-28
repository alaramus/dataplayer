# The server's log

Date: 2026-09-28. Decision: D184.

## The problem

Asked where the server's errors go, the honest answer was: to the standard
output of the backend container, and nowhere else.

- `docker compose logs backend` was the only way to read it, and rebuilding the
  container, which development does many times a day, emptied it.
- Nothing configured logging. The level came from a `logging.basicConfig` that
  ran as a side effect of importing the mail module.
- What was there was mostly uvicorn's access lines, a health check every ten
  seconds among them.
- A failure of a source that the driver could not name — a table dropped under
  a query, a privilege missing, a bug in our own code inside a driver call —
  became "Query failed". The exception was re-raised `from None` and written
  nowhere. The person saw a sentence that explained nothing, and there was no
  record anywhere of what had happened.
- Where failures were logged in full — jobs, query runs — a psycopg message
  could carry the connection string with its password, which ENGINEERING.md
  forbids.
- Agent failures were logged by type name alone: no place, no way to find the
  one somebody reported.

The person asked for three things: to know where errors are kept and that the
real ones are, for a superuser to read them, and a button beside Services and
Terminals that opens them in the panel at the foot of the screen.

## D184. The server writes down what went wrong, whole, and a superuser reads it

**Files that outlive the container.** One configuration per process,
`core.logs.configure`, called by the backend before it builds the application
and by the metrics collector. Standard output keeps the text it had. With
`LOG_DIR` set — Compose sets it on a volume of its own — each process also
writes `backend.log` or `metrics.log` as JSON lines, rotated by size, five
files of ten megabytes by default. Uvicorn configures its loggers before the
application is imported; configuring after it replaces their handlers, so
requests and tracebacks go through the same two handlers.

**Everything a request did.** The person chose to see requests as well as
failures, so access lines are kept; the health check is not, because it is
Docker asking, not a person, and neither is the panel reading the log while it
follows it, which would otherwise fill the log with itself. Every entry written while a request is answered
carries its method and path, without the query string.

**No secrets.** Both formats pass through `redact`, which masks a password in
an address, `password=`, `token=`, `ticket=` and `api_key=` in the spellings a
DSN, an environment line, a query string and JSON use, and a bearer token.

**A ref ties the sentence to the entry.** An unexpected failure is written at
ERROR with its traceback and a six-character ref from an alphabet nobody
misreads, and the sentence the person sees ends in `· ref K7Q3PD`. The ref is
part of the message rather than a field beside it, so it reaches every place a
message already goes — the grid's banner, a job's result, a query run, an
agent's answer — without a route learning anything new. The places:

- an exception that reaches the new `RecordFailures` middleware, which answers
  500 with the sentence and the ref, inside CORS so a browser can read it;
- a PostgreSQL failure `classify` falls back on, and the last branch of the
  Redis and SSH reducers;
- a job that raised, a query run that broke;
- an agent or quick-chat answer that no provider sentence explains.

An expected failure — a refused password, an unreachable host, a timeout, a
command the server refused — is an answer about the source, shown as it was,
and gets no ref. Logging it with a traceback every time the health monitor
probed a dead server would bury the rest.

**Private text stays private.** A query run and an agent answer are logged by
the exception's type and the frames it passed through, never its text: the
statement somebody ran, and what a provider echoed of a conversation, belong
to them and not to whoever operates the server.

**A superuser's panel.** `GET /logs/` needs a superuser. It reads each
process's files from the end, newest first across rotation, keeps what matches
the level (everything, warnings and errors, errors), the process and the words
(a ref, a path, a message, a traceback), merges the two processes by time and
answers a page. `before` pages back; `after` would follow. It reads at most
32 MB per process per request, so a search through a large log answers "there
may be more" rather than stalling. On the rail, **Logs** stands beside Services,
Terminals and Queries; a block marked `superuserOnly` is left out of the rail
for anybody else, rather than rendering an empty block that keeps its padding.
The panel follows the log every three seconds unless told not to, colours a
line by its level or, for a request, by its status, and opens an entry to its
request, ref, message and traceback with a Copy.

## Rejected

- **A table of errors in the application database.** Structured and easy to
  filter, but requests would not be in it, and the log would stop working at
  exactly the moment the database did.
- **Reading Docker's log through its socket.** It would give a superuser's
  panel the Docker socket, and it still loses everything at a rebuild.
- **A ref as a field of every error response.** Sixty places turn an
  `AdapterError` into a response, and jobs, runs and answers carry messages,
  not responses. A ref inside the message reaches all of them unchanged.
- **Logging expected source failures.** The connection's own state and the
  sentence already say them, and the health monitor would repeat them every
  interval.

## Known deviations

- The prestart container and the reloading parent of `fastapi dev` write to
  standard output alone.
- An access line is INFO whatever it answered; the panel colours it by status.
- A ref lives in a sentence and in the log. When the log rotates past it, the
  sentence names an entry that is gone.
