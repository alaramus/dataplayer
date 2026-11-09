# The RabbitMQ console

Decision D328. The second slice of the RabbitMQ source: `rabbitmqadmin` in a
terminal, as Kafka's tools are Kafka's (D286, D307). The user asked for a
console when the source was planned and left its slice to be chosen.

## Which program

RabbitMQ ships three command-line tools, and only one of them is a client:

- `rabbitmqctl` and `rabbitmq-diagnostics` — rejected: they speak Erlang
  distribution to a node and need its cookie and its port 25672, which a
  broker does not expose to clients and a cloud one never does;
- `rabbitmqadmin` version 1, a Python script — rejected: deprecated, and gone
  from the official images;
- `rabbitmqadmin` version 2 — chosen: a client of the same management API the
  catalog reads (D325), so whatever the catalog reaches it reaches. It lists,
  shows, declares, deletes, purges, publishes, gets and exports definitions.

The official `rabbitmq:<version>-management` images carry it since the
images moved from the Python version (docker-library/rabbitmq#780); 4.3.7,
the test server's release, has 2.35.0 at `/usr/local/bin`. The terminal is
bash in that image, so `rabbitmqadmin`'s own bash completion is offered too.

## The settings and the password

`rabbitmqadmin` reads a node's address, user, password, virtual host and CA
bundle from a TOML file, from its environment, or from flags. Flags are
visible to anything that lists processes; a variable stays in the shell for
`env` to print. So, as Kafka's settings are (D307), the server composes the
file — one `[default]` node — and it is written inside the container at start
from a variable that is unset before the prompt, with the CA certificate the
same way. `RABBITMQADMIN_CONFIG_FILE_PATH` names the file, so every command
uses the connection unless it names another node or address itself.

The file's text is composed by the server: every value is a TOML basic string
with its quote, backslash and control characters escaped, so nothing in a
password can end the value. Every value reaches the shell through the
environment and is written with `printf '%s'`, never read as shell syntax.

The virtual host is the connection's, or `/` when it names none; `-V` picks
another for one command.

A greeting above the prompt says the tool is set up for the connection and
gives three commands to start from.

## The slices that remain

Writes and Peek, reports, metrics and search, and the service template stay
as the source spec lists them, renumbered 3 to 5.
