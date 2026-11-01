# The Kafka console

Decision D307. The second slice of the Kafka source: Kafka's own command-line
tools in a terminal, as zkCli is ZooKeeper's (D286, D299). The user chose the
tools over a console of the application's own when the source was planned.

## Which program

Kafka has no single client shell: it has forty scripts, `kafka-topics.sh`,
`kafka-console-consumer.sh`, `kafka-consumer-groups.sh` and the rest, each
told the brokers with `--bootstrap-server` and the client settings with
`--command-config`. In the 4.3 image every tool that talks to a cluster takes
both under those names. So the terminal is bash in the `apache/kafka` image,
of the release the test server runs, with the tools on the path.

Three ways were weighed:

- a bare shell and a greeting naming two variables to pass — rejected: every
  command would carry two flags nobody remembers;
- `kcat` — rejected: a different tool from the one Kafka's documentation and
  every answer about Kafka use, and it covers producing and consuming only;
- each tool that takes both flags wrapped by a shell function of the same
  name that adds them, unless the command names brokers itself — chosen.
  `kafka-topics.sh --list` lists this connection's topics, and pointing one at
  another cluster still works.

The tools wrapped are the ones whose help in that image lists both flags,
read when the slice was written; the scripts that start servers, read files
or take neither are left as they are.

## The settings and the password

The client settings — the security protocol, the SASL mechanism and its JAAS
line with the user and password, a CA certificate as a PEM truststore — are
written into a properties file inside the container when it starts, from the
environment, and the variables are unset before the prompt. The password is
in the environment, never in the arguments, by D87's rule, and in a file
inside a container that is removed when the terminal closes.

The file's text is composed by the server: the JAAS line quotes the user and
password with its own escaping, and the properties format escapes again, so a
quote or a backslash in a password cannot end the value. Every value reaches
the shell through the environment and is written with `printf '%s'`, so none
is ever read as shell syntax.

A greeting above the prompt says the tools are set up for the connection and
gives three commands to start from.
