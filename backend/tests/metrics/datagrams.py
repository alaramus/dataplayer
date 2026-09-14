"""DPMA/1 datagrams as dataplayer-monitor-agent signs them, for tests."""

import base64
import hashlib
import hmac
import json
from typing import Any

INSTANCE = "6f1c2d3e-0000-4000-8000-000000000001"
BOOT = "1b2c3d4e-0000-4000-8000-000000000001"


def header(
    kind: str,
    *,
    time: int,
    seq: int = 1,
    host: str = "web-01",
    instance: str = INSTANCE,
    started: int | None = None,
    boot: str = BOOT,
) -> dict[str, Any]:
    return {
        "v": 1,
        "agent": {"version": "0.1.1", "instance": instance, "started": time - 60 if started is None else started},
        "host": {"name": host, "boot": boot},
        "seq": seq,
        "time": time,
        "kind": kind,
    }


def metrics(samples: list[list[object]], **fields: Any) -> dict[str, Any]:
    return {**header("metrics", **fields), "samples": samples}


def processes(rows: list[list[object]], *, total: int = 200, part: tuple[int, int] = (1, 1), **fields: Any) -> dict[str, Any]:
    return {**header("processes", **fields), "total": total, "part": list(part), "rows": rows}


def process(pid: int, cpu: float = 1.0, memory: float = 1.0, command: str = "", name: str = "worker") -> list[object]:
    return [pid, 1, "root", "S", cpu, memory, 1_048_576 * pid, 1_789_000_000, name, command or f"{name} {pid}"]


def host(**fields: Any) -> dict[str, Any]:
    return {
        **header("host", **fields),
        "info": {
            "os": "Ubuntu 24.04.1 LTS",
            "kernel": "6.8.0-45-generic",
            "arch": "amd64",
            "cpus": 8,
            "cpu_model": "Intel(R) Xeon(R)",
            "memory": 16_701_304_832,
            "boot_time": 1_789_000_000,
            "collectors": {"cpu": 15, "processes": 60},
        },
    }


def key_id(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def signed(key: str, body: dict[str, Any] | bytes, *, kid: str | None = None) -> bytes:
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    signature = base64.urlsafe_b64encode(hmac.new(key.encode(), raw, hashlib.sha256).digest()).rstrip(b"=")
    return b"DPMA/1 " + (kid or key_id(key)).encode() + b" " + signature + b"\n" + raw
