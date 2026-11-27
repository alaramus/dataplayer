"""Kafka's own tools as a Kafka connection's terminal (D286, D307).

bash in the image the test server runs, where each tool that takes
`--bootstrap-server` and `--command-config` is wrapped by a function of its own
name that adds both for this connection, unless the command names brokers
itself. The client settings, password included, are composed here and written
into a file inside the container at start; every value reaches the shell
through its environment and is written with `printf '%s'`, so none is ever
read as shell syntax.
"""

from app.adapters.kafka.options import (
    MECHANISMS,
    KafkaAwsMskIam,
    KafkaNoAuth,
    KafkaOptions,
)
from app.adapters.kafka.session import KafkaSession
from app.adapters.protocol import AdapterError
from app.adapters.terminal import ConsoleProgram
from app.adapters.tls import PROGRAM_PAIR, program_paths, with_program_files
from app.core.translation import say

IMAGE = "apache/kafka:4.3.2"

BOOTSTRAP_VARIABLE = "KAFKA_BOOTSTRAP"
CONFIG_VARIABLE = "KAFKA_CONFIG"
PROPERTIES_VARIABLE = "DP_PROPERTIES"
RC_VARIABLE = "DP_RC"
NOTE_VARIABLE = "DP_NOTE"

CONFIG_PATH = "/tmp/client.properties"
RC_PATH = "/tmp/kafkarc"

# The tools whose help in the 4.3 image lists both flags. The ones that start
# servers, read files or take neither are left as they are.
WRAPPED = (
    "kafka-acls.sh",
    "kafka-broker-api-versions.sh",
    "kafka-client-metrics.sh",
    "kafka-configs.sh",
    "kafka-console-consumer.sh",
    "kafka-console-producer.sh",
    "kafka-console-share-consumer.sh",
    "kafka-consumer-groups.sh",
    "kafka-delegation-tokens.sh",
    "kafka-delete-records.sh",
    "kafka-features.sh",
    "kafka-get-offsets.sh",
    "kafka-groups.sh",
    "kafka-leader-election.sh",
    "kafka-log-dirs.sh",
    "kafka-metadata-quorum.sh",
    "kafka-reassign-partitions.sh",
    "kafka-share-groups.sh",
    "kafka-streams-groups.sh",
    "kafka-topics.sh",
    "kafka-transactions.sh",
)

_JAAS_MODULES = {
    "plain": "org.apache.kafka.common.security.plain.PlainLoginModule",
    "scram-sha-256": "org.apache.kafka.common.security.scram.ScramLoginModule",
    "scram-sha-512": "org.apache.kafka.common.security.scram.ScramLoginModule",
}


def _jaas_quoted(text: str) -> str:
    """A JAAS option value: a quote and a backslash escaped by a backslash."""
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _property(key: str, value: str) -> str:
    """One line of a Java properties file, its value escaped as the format reads it."""
    escaped = (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    # A leading space would be taken for the separator's.
    if escaped.startswith(" "):
        escaped = "\\" + escaped
    return f"{key}={escaped}"


def client_properties(options: KafkaOptions) -> str:
    """The settings Kafka's Java tools read, the same ones the adapter uses."""
    if isinstance(options, KafkaAwsMskIam):
        # Kafka's tools sign in to MSK with AWS's own plugin, a jar the image
        # does not carry (D453).
        raise AdapterError("config", say("Kafka's tools in a terminal cannot sign in with AWS IAM yet"))
    config = KafkaSession(options).config()
    lines = [
        _property("security.protocol", str(config["security.protocol"])),
        _property("client.id", "dataplayer-console"),
    ]
    if not isinstance(options, KafkaNoAuth):
        lines.append(_property("sasl.mechanism", MECHANISMS[options.auth_method]))
        jaas = (
            f"{_JAAS_MODULES[options.auth_method]} required "
            f"username={_jaas_quoted(options.user)} "
            f"password={_jaas_quoted(options.password.get_secret_value())};"
        )
        lines.append(_property("sasl.jaas.config", jaas))
    settings = options.tls()
    if settings.enabled:
        # Java's client checks every certificate it is given; only the name
        # can be left out (D446).
        if not settings.verifies:
            raise AdapterError(
                "config",
                say("Kafka's tools check the brokers' certificates; choose Verify CA or Verify full"),
            )
        if settings.mode == "verify_ca":
            lines.append(_property("ssl.endpoint.identification.algorithm", ""))
        paths = program_paths(settings)
        if paths.ca:
            lines.append(_property("ssl.truststore.type", "PEM"))
            lines.append(_property("ssl.truststore.location", paths.ca))
        if paths.certificate:
            lines.append(_property("ssl.keystore.type", "PEM"))
            lines.append(_property("ssl.keystore.location", PROGRAM_PAIR))
    return "\n".join(lines) + "\n"


def _rc() -> str:
    """bash's start file: the wrappers, the variables gone, the greeting."""
    lines = [
        'export PATH="/opt/kafka/bin:$PATH"',
        f"unset {PROPERTIES_VARIABLE} {RC_VARIABLE}",
        "_dp_run() {",
        '  local tool="$1"; shift',
        '  for arg in "$@"; do',
        '    case "$arg" in --bootstrap-server|--bootstrap-server=*|--bootstrap-controller|--bootstrap-controller=*)',
        '      command "$tool" "$@"; return;;',
        "    esac",
        "  done",
        f'  command "$tool" --bootstrap-server "${BOOTSTRAP_VARIABLE}" --command-config "${CONFIG_VARIABLE}" "$@"',
        "}",
    ]
    lines += [f'{tool}() {{ _dp_run {tool} "$@"; }}' for tool in WRAPPED]
    lines += [
        "PS1='kafka> '",
        f'printf "%s\\n\\n" "${NOTE_VARIABLE}"',
        f"unset {NOTE_VARIABLE}",
    ]
    return "\n".join(lines) + "\n"


# The settings and the start file written, then bash in the shell's place.
_SCRIPT = (
    f'umask 077; printf "%s" "${PROPERTIES_VARIABLE}" > {CONFIG_PATH}; '
    f'printf "%s" "${RC_VARIABLE}" > {RC_PATH}; '
    f"exec bash --rcfile {RC_PATH} -i"
)


def console_program(options: KafkaOptions) -> ConsoleProgram:
    environment = {
        BOOTSTRAP_VARIABLE: options.bootstrap_servers,
        CONFIG_VARIABLE: CONFIG_PATH,
        PROPERTIES_VARIABLE: client_properties(options),
        RC_VARIABLE: _rc(),
        NOTE_VARIABLE: say(
            "Kafka's tools are set up for this connection. Try: "
            "kafka-topics.sh --list · "
            "kafka-console-consumer.sh --topic NAME --from-beginning · "
            "kafka-consumer-groups.sh --describe --all-groups"
        ),
    }
    argv, files = with_program_files(("sh", "-c", _SCRIPT), options.tls())
    return ConsoleProgram(image=IMAGE, argv=argv, environment={**environment, **files})
