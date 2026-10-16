import type { AgentHost, ProcessInfo } from "@/client"
import { t } from "@/shared/i18n"
import type { MessageKey } from "@/shared/i18n"

import { duration, formatValue } from "./seriesFormat"

/**
 * What a host of an agent is, and a process on it, as a person reads it (D130).
 */

export function systemWording(host: AgentHost): string {
  const known = [host.os, host.arch].filter((part): part is string => typeof part === "string" && part !== "")
  return known.length === 0 ? t("dashboards.host.not_described") : known.join(" · ")
}

/** What does not fit a row: the agent's version, the kernel, the processor and what it collects. */
export function hostDetailWording(host: AgentHost): string {
  const agent = t("dashboards.host.agent", { version: host.agent_version })
  if (host.kernel === null || host.kernel === undefined) return agent
  return [
    agent,
    t("dashboards.host.kernel", { kernel: host.kernel }),
    host.cpu_model ?? "",
    t("dashboards.host.collects", { collectors: collectorsWording(host) }),
  ]
    .filter((part) => part !== "")
    .join(", ")
}

export function hardwareWording(host: AgentHost): string {
  const parts: string[] = []
  if (typeof host.cpus === "number") parts.push(t("dashboards.host.cpus", { n: host.cpus }, host.cpus))
  if (typeof host.memory_bytes === "number") parts.push(formatValue(host.memory_bytes, "B"))
  return parts.length === 0 ? "—" : parts.join(" · ")
}

/** How long the host has been up, from its boot. */
export function upWording(host: AgentHost, nowMs: number): string {
  if (host.booted_at === null || host.booted_at === undefined) return "—"
  return duration((nowMs - Date.parse(host.booted_at)) / 1000)
}

/** The collectors the agent runs, in the order it lists them. */
export function collectorsWording(host: AgentHost): string {
  const entries = Object.entries(host.collectors ?? {})
  if (entries.length === 0) return "—"
  return entries.map(([name, seconds]) => `${name} ${t("dashboards.duration.seconds", { s: seconds })}`).join(", ")
}

const STATES: Record<string, MessageKey> = {
  R: "dashboards.process_state.running",
  S: "dashboards.process_state.sleeping",
  D: "dashboards.process_state.waiting_io",
  Z: "dashboards.process_state.zombie",
  T: "dashboards.process_state.stopped",
  t: "dashboards.process_state.traced",
  I: "dashboards.process_state.idle",
  X: "dashboards.process_state.dead",
}

export function stateWording(state: string): string {
  const key = STATES[state]
  return key === undefined ? state : t(key)
}

/** A kernel thread has no command line; it is shown by name, as `ps` does. */
export function commandWording(process: ProcessInfo): string {
  return process.command === "" ? `[${process.name}]` : process.command
}

export function runningForWording(process: ProcessInfo, nowMs: number): string {
  return duration((nowMs - Date.parse(process.started_at)) / 1000)
}
