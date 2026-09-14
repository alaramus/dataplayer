import { describe, expect, it } from "vitest"

import type { AgentHost, ProcessInfo } from "@/client"

import {
  collectorsWording,
  commandWording,
  hardwareWording,
  hostDetailWording,
  runningForWording,
  stateWording,
  systemWording,
  upWording,
} from "./hostFacts"

const NOW = Date.parse("2026-09-14T12:00:00Z")

const described: AgentHost = {
  agent_id: "agent-1",
  agent_name: "office",
  host: "web-01",
  agent_version: "0.1.1",
  agent_started: "2026-09-14T11:00:00Z",
  last_seen: "2026-09-14T11:59:50Z",
  os: "Ubuntu 24.04.1 LTS",
  kernel: "6.8.0-45-generic",
  arch: "amd64",
  cpus: 8,
  cpu_model: "Intel(R) Xeon(R)",
  memory_bytes: 16 * 1024 ** 3,
  booted_at: "2026-09-11T08:00:00Z",
  collectors: { cpu: 15, processes: 60 },
}

const fresh: AgentHost = {
  agent_id: "agent-1",
  agent_name: "office",
  host: "new-01",
  agent_version: "0.1.1",
  agent_started: "2026-09-14T11:59:55Z",
}

describe("what a host is", () => {
  it("names its system, hardware, uptime and collectors", () => {
    expect(systemWording(described)).toBe("Ubuntu 24.04.1 LTS · amd64")
    expect(hostDetailWording(described)).toBe(
      "Agent 0.1.1, kernel 6.8.0-45-generic, Intel(R) Xeon(R), collects cpu 15 s, processes 60 s"
    )
    expect(hardwareWording(described)).toBe("8 CPUs · 16 GB")
    expect(upWording(described, NOW)).toBe("3 d 4 h")
    expect(collectorsWording(described)).toBe("cpu 15 s, processes 60 s")
  })

  it("says so before the agent has described it", () => {
    expect(systemWording(fresh)).toBe("Not described yet")
    expect(hostDetailWording(fresh)).toBe("Agent 0.1.1")
    expect(hardwareWording(fresh)).toBe("—")
    expect(upWording(fresh, NOW)).toBe("—")
    expect(collectorsWording(fresh)).toBe("—")
    expect(hardwareWording({ ...fresh, cpus: 1 })).toBe("1 CPU")
  })
})

describe("a process on it", () => {
  const worker: ProcessInfo = {
    pid: 42,
    ppid: 1,
    user: "postgres",
    state: "S",
    pcpu: 3.5,
    pmem: 1.2,
    rss_bytes: 104857600,
    started_at: "2026-09-14T09:30:00Z",
    name: "postgres",
    command: "postgres: checkpointer",
  }

  it("reads its state, its command and how long it has run", () => {
    expect(stateWording("D")).toBe("Waiting on I/O")
    expect(stateWording("W")).toBe("W")
    expect(commandWording(worker)).toBe("postgres: checkpointer")
    expect(commandWording({ ...worker, command: "", name: "kworker/0:1" })).toBe("[kworker/0:1]")
    expect(runningForWording(worker, NOW)).toBe("2 h 30 min")
  })
})
