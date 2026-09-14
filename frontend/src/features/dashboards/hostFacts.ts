import type { AgentHost, ProcessInfo } from "@/client"

import { duration, formatValue } from "./seriesFormat"

/**
 * What a host of an agent is, and a process on it, as a person reads it (D130).
 */

export function systemWording(host: AgentHost): string {
  const known = [host.os, host.arch].filter((part): part is string => typeof part === "string" && part !== "")
  return known.length === 0 ? "Not described yet" : known.join(" · ")
}

/** What does not fit a row: the agent's version, the kernel, the processor and what it collects. */
export function hostDetailWording(host: AgentHost): string {
  const agent = `Agent ${host.agent_version}`
  if (host.kernel === null || host.kernel === undefined) return agent
  return [agent, `kernel ${host.kernel}`, host.cpu_model ?? "", `collects ${collectorsWording(host)}`]
    .filter((part) => part !== "")
    .join(", ")
}

export function hardwareWording(host: AgentHost): string {
  const parts: string[] = []
  if (typeof host.cpus === "number") parts.push(host.cpus === 1 ? "1 CPU" : `${String(host.cpus)} CPUs`)
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
  return entries.map(([name, seconds]) => `${name} ${String(seconds)} s`).join(", ")
}

const STATES: Record<string, string> = {
  R: "Running",
  S: "Sleeping",
  D: "Waiting on I/O",
  Z: "Zombie",
  T: "Stopped",
  t: "Traced",
  I: "Idle",
  X: "Dead",
}

export function stateWording(state: string): string {
  return STATES[state] ?? state
}

/** A kernel thread has no command line; it is shown by name, as `ps` does. */
export function commandWording(process: ProcessInfo): string {
  return process.command === "" ? `[${process.name}]` : process.command
}

export function runningForWording(process: ProcessInfo, nowMs: number): string {
  return duration((nowMs - Date.parse(process.started_at)) / 1000)
}
