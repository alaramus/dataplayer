/** The server's log (features/logs). */
export const logs = {
  logs: "Logs",
  tooltip: "The server's log",
  levels: {
    all: "Everything",
    warning: "Warnings and errors",
    error: "Errors",
  },
  processes: {
    all: "Every process",
    backend: "Backend",
    metrics: "Metrics",
    search_keeper: "Search index",
  },
  only_superuser: "Only a superuser can read the server's log.",
  search: "Search the text, a ref or a path",
  follow: "Follow",
  reload: "Read the log again",
  read_failed: "The log could not be read",
  not_kept: "This server keeps no log files. Set LOG_DIR to keep them; until then the log is on the server's standard output.",
  nothing: "Nothing in the log matches.",
  ref: "ref {ref}",
  copy: "Copy this entry",
  copied: "Copied",
  copy_refused: "The browser did not allow copying",
  older: "Older entries",
}
