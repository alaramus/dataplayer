"""Reading what `sys_monitor_agent` 1.14.0 sends (D130).

The packets below are shaped exactly as the agent sent them on 2026-09-13,
shortened where a list repeats.
"""

import json

from app.metrics.packets import (
    MAX_PACKET_BYTES,
    Envelope,
    ProcessRow,
    ProcessSnapshot,
    Sample,
    agent_process_of,
    elapsed_seconds,
    is_header_row,
    process_snapshot_of,
    read_envelope,
    samples_of,
)

CPU = (
    b'{"action":   "monitor-cpu","appkey":"KEY","host":"b641829ceeb6",'
    b'"time":"1789279023","data":{"cpu":[0.708629,0.000000,0.990099],'
    b'"uptime":1715,"loadavg":[0.094727,0.106445,0.088379]}}'
)
DISK = (
    b'{"action":   "monitor-disk","appkey":"KEY","host":"h","time":"1789279055",'
    b'"data":[{"mounted":"/","total":1081101176832,"free":1058199871488,"usage":2}]}'
)
DF = (
    b'{"action":   "monitor-df","appkey":"KEY","host":"h","time":"1789279055",'
    b'"data":[{"Filesystem":"overlay","1K-blocks":"1055762868","Used":"22364556",'
    b'"Available":"979694840","Use%":"3%","Mounted_on":"/"}]}'
)
NET = (
    b'{"action":   "monitor-net","appkey":"KEY","host":"h","time":"1789279056",'
    b'"data":[{ "name":"lo:", "read":0.000000, "transfer":0.000000},'
    b'{ "name":"eth0:", "read":1.448276, "transfer":130.482758}]}'
)
MEMORY = (
    b'{"action":   "monitor-memory","appkey":"KEY","host":"h","time":"1789279056",'
    b'"data":[{"MemTotal":15917216},{"MemFree":13880616},{"SwapCached":0}]}'
)
TCP = (
    b'{"action":   "monitor-tcp","appkey":"KEY","host":"h","time":"1789279055",'
    b'"data":[{"State":"State","Recv-Q":"Recv-Q","Send-Q":"Send-Q",'
    b'"Local:Address:Port":"Local:Address:Port","Peer:Address:Port":"Peer:Address:PortProcess"},'
    b'{"State":"LISTEN","Recv-Q":"0","Send-Q":"4096","Local:Address:Port":"127.0.0.11:36759",'
    b'"Peer:Address:Port":"0.0.0.0:*","Process":""}]}'
)
PS = (
    b'{"action":   "monitor-ps","appkey":"KEY","host":"h","time":"1789279055",'
    b'"data":[{"PCPU":"%CPU","PMEM":"%MEM","PID":"PID","PPID":"PPID","USER":"USER",'
    b'"ELAPSED":"ELAPSED","COMMAND":"COMMAND"},'
    b'{"PCPU":"0.0","PMEM":"0.1","PID":"1","PPID":"0","USER":"root","ELAPSED":"00:32",'
    b'"COMMAND":"./sys_monitor_agent 192.168.65.254 9999 30"},'
    b'{"PCPU":"n/a","PMEM":"0.0","PID":"12","PPID":"1","USER":"root","ELAPSED":"00:32",'
    b'"COMMAND":"/bin/sh ./run-iftop.sh"}]}'
)


def _envelope(raw: bytes) -> Envelope:
    envelope = read_envelope(raw)
    assert envelope is not None
    return envelope


def _by_series(samples: list[Sample]) -> dict[tuple[str, str], Sample]:
    return {(sample.field, sample.label): sample for sample in samples}


def test_an_envelope_names_the_key_host_metric_and_moment() -> None:
    envelope = _envelope(CPU)

    assert envelope.key == "KEY"
    assert envelope.host == "b641829ceeb6"
    assert envelope.metric == "cpu"
    assert envelope.ts == 1789279023


def test_a_packet_that_cannot_be_addressed_is_refused() -> None:
    assert read_envelope(b"not json") is None
    assert read_envelope(b"[1, 2]") is None
    assert read_envelope(json.dumps({"action": "monitor-cpu", "host": "h", "time": "1"}).encode()) is None
    assert read_envelope(json.dumps({"action": "monitor-cpu", "appkey": "K", "host": "h", "time": "soon"}).encode()) is None
    assert read_envelope(json.dumps({"action": "monitor-", "appkey": "K", "host": "h", "time": "1"}).encode()) is None
    assert read_envelope(b" " * (MAX_PACKET_BYTES + 1)) is None


def test_a_millisecond_timestamp_is_read_as_seconds() -> None:
    raw = json.dumps(
        {"action": "monitor-x", "appkey": "K", "host": "h", "time": 1789279023123, "data": {}}
    ).encode()

    assert _envelope(raw).ts == 1789279023


def test_cpu_names_the_total_and_each_core_and_the_load_windows() -> None:
    series = _by_series(samples_of(_envelope(CPU)))

    assert set(series) == {
        ("cpu", "total"),
        ("cpu", "cpu0"),
        ("cpu", "cpu1"),
        ("uptime", ""),
        ("loadavg", "1m"),
        ("loadavg", "5m"),
        ("loadavg", "15m"),
    }
    assert series[("cpu", "total")].unit == "%"
    assert series[("uptime", "")].value == 1715
    assert series[("uptime", "")].unit == "s"


def test_a_row_is_labelled_by_the_column_that_names_it() -> None:
    disk = _by_series(samples_of(_envelope(DISK)))
    df = _by_series(samples_of(_envelope(DF)))

    assert set(disk) == {("total", "/"), ("free", "/"), ("usage", "/")}
    assert disk[("total", "/")].unit == "B"
    # `Mounted_on` comes before `Filesystem` in the label order, and neither
    # becomes a series of its own.
    assert set(df) == {
        ("1K-blocks", "/"),
        ("Used", "/"),
        ("Available", "/"),
        ("Use%", "/"),
    }


def test_numbers_sent_as_text_are_numbers() -> None:
    df = _by_series(samples_of(_envelope(DF)))

    assert df[("Used", "/")].value == 22364556
    assert df[("Use%", "/")].value == 3
    assert df[("Use%", "/")].unit == "%"


def test_an_interface_loses_the_colon_of_the_file_it_came_from() -> None:
    net = _by_series(samples_of(_envelope(NET)))

    assert ("read", "eth0") in net
    assert ("transfer", "lo") in net


def test_a_line_of_meminfo_is_labelled_by_nothing_rather_than_its_position() -> None:
    memory = _by_series(samples_of(_envelope(MEMORY)))

    assert set(memory) == {("MemTotal", ""), ("MemFree", ""), ("SwapCached", "")}
    assert memory[("MemTotal", "")].unit == "kB"


def test_the_socket_table_is_a_count_per_state_and_the_echoed_header_is_not_a_socket() -> None:
    tcp = _by_series(samples_of(_envelope(TCP)))

    assert tcp == {
        ("count", "LISTEN"): Sample("tcp", "count", "LISTEN", "", 1789279055, 1.0),
        ("count", "total"): Sample("tcp", "count", "total", "", 1789279055, 1.0),
    }


def test_an_empty_socket_table_still_says_zero() -> None:
    raw = json.dumps(
        {"action": "monitor-tcp", "appkey": "K", "host": "h", "time": "5", "data": []}
    ).encode()

    assert samples_of(_envelope(raw)) == [Sample("tcp", "count", "total", "", 5, 0.0)]


def test_the_process_tables_are_not_series() -> None:
    assert samples_of(_envelope(PS)) == []
    python = PS.replace(b"monitor-ps", b"monitor-python")
    assert samples_of(_envelope(python)) == []


def test_a_process_table_is_a_snapshot_without_its_header() -> None:
    snapshot = process_snapshot_of(_envelope(PS))

    assert snapshot is not None
    assert snapshot.host == "h"
    assert [row.pid for row in snapshot.rows] == [1]
    assert snapshot.rows[0].command.startswith("./sys_monitor_agent")
    assert snapshot.rows[0].pmem == 0.1
    # The row with an unreadable percentage is counted, the header is not.
    assert snapshot.skipped == 1


def test_only_a_process_packet_has_a_snapshot() -> None:
    assert process_snapshot_of(_envelope(CPU)) is None


def test_values_that_are_not_measurements_are_skipped() -> None:
    raw = json.dumps(
        {
            "action": "monitor-x",
            "appkey": "K",
            "host": "h",
            "time": "5",
            "data": {"flag": True, "word": "up", "empty": "", "nan": "NaN", "ok": "7"},
        }
    ).encode()

    assert [(s.field, s.value) for s in samples_of(_envelope(raw))] == [("ok", 7.0)]


def test_iftop_charts_its_rates_and_counts_its_flows() -> None:
    raw = json.dumps(
        {
            "action": "monitor-iftop",
            "appkey": "K",
            "host": "h",
            "time": "5",
            "data": [
                [{"IP": "10.0.0.1:443"}, {"TXRX": "TX"}, {"2sec": "1.00Kb"}],
                [{"IP": "10.0.0.1:443"}, {"TXRX": "RX"}, {"2sec": "2.00Kb"}],
                {"Total send rate": [{"2sec": "1.00Kb"}, {"cumulative": "2KB"}]},
                {"Peak rate (sent/received/total)": [{"2sec": "9Kb"}]},
            ],
        }
    ).encode()

    series = _by_series(samples_of(_envelope(raw)))

    assert series[("Total send rate", "2sec")].value == 1024
    assert series[("Total send rate", "2sec")].unit == "b/s"
    assert series[("Total send rate", "cumulative")].unit == "B"
    assert series[("peers", "")].value == 1
    assert not any(field.startswith("Peak rate") for field, _ in series)


def test_a_header_needs_two_echoes() -> None:
    assert is_header_row({"A": "A", "B": "B"})
    assert not is_header_row({"A": "A", "B": "x"})
    assert not is_header_row({"A": "A", "B": 1})


def test_elapsed_time_is_read_the_way_ps_prints_it() -> None:
    assert elapsed_seconds("00:32") == 32
    assert elapsed_seconds("05:11") == 311
    assert elapsed_seconds("01:02:03") == 3723
    assert elapsed_seconds("2-01:02:03") == 2 * 86400 + 3723
    assert elapsed_seconds("ELAPSED") is None
    assert elapsed_seconds("1:2:3:4") is None
    assert elapsed_seconds("x-00:10") is None


def test_the_agent_s_own_row_says_when_it_started_and_what_it_runs() -> None:
    # The command line as the agent ran on 2026-09-13, crashing every 33 s.
    command = (
        "./sys_monitor_agent 192.168.65.254 9998 30 "
        "--actions=tcp:30,disk:30[/],ps:30,df:30[/],net:30,memory:30,cpu:30,iftop:30 "
        "--sysroot= --apikey=SINKKEY --securekey= --slackpath="
    )
    snapshot = ProcessSnapshot(
        host="crash-sink",
        ts=1_789_301_589,
        rows=[
            ProcessRow(1, 0, "root", command, 0.0, 0.0, "00:32"),
            ProcessRow(12, 1, "root", "/bin/sh ./run-iftop.sh", 0.0, 0.0, "00:32"),
        ],
        skipped=0,
        truncated=0,
    )

    agent = agent_process_of(snapshot)

    assert agent is not None
    assert agent.started == 1_789_301_557
    assert agent.actions == ("tcp", "disk", "ps", "df", "net", "memory", "cpu", "iftop")


def test_a_table_without_the_agent_says_nothing_of_it() -> None:
    snapshot = process_snapshot_of(_envelope(PS))
    assert snapshot is not None
    without = ProcessSnapshot("h", 1, [row for row in snapshot.rows if row.pid != 1], 0, 0)

    assert agent_process_of(without) is None
    found = agent_process_of(snapshot)
    assert found is not None
    assert found.actions == ()
