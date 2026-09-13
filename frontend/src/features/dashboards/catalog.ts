/**
 * The catalog of what a person's agents reported, as an index and as a tree.
 *
 * A saved widget holds series ids and nothing else, so the legend, the unit and
 * the title are looked up here on every read: a host renamed on the agent side
 * shows its new name rather than one stored in the widget.
 */

import type { MetricsCatalog } from "@/client"
import type { TreeNodes } from "@/shared/ui"

export interface SeriesEntry {
  id: number
  agentId: string
  agentName: string
  host: string
  metric: string
  field: string
  label: string
  unit: string
  lastSeen: string
}

export function indexCatalog(catalog: MetricsCatalog | undefined): Map<number, SeriesEntry> {
  const index = new Map<number, SeriesEntry>()
  for (const agent of catalog?.agents ?? []) {
    for (const host of agent.hosts) {
      for (const metric of host.metrics) {
        for (const series of metric.series) {
          index.set(series.id, {
            id: series.id,
            agentId: agent.agent_id,
            agentName: agent.name,
            host: host.host,
            metric: metric.metric,
            field: series.field,
            label: series.label,
            unit: series.unit,
            lastSeen: series.last_seen,
          })
        }
      }
    }
  }
  return index
}

/** "cpu total", or "web-01 · cpu total" where hosts have to be told apart. */
export function seriesName(entry: SeriesEntry, withHost: boolean): string {
  const name = entry.label ? `${entry.field} ${entry.label}` : entry.field
  return withHost ? `${entry.host} · ${name}` : name
}

const SERIES_PREFIX = "series:"

export function seriesKey(id: number): string {
  return `${SERIES_PREFIX}${String(id)}`
}

/** The series among ticked tree keys. Keys are this module's own. */
export function tickedSeries(ticked: readonly string[]): number[] {
  return ticked
    .filter((key) => key.startsWith(SERIES_PREFIX))
    .map((key) => Number(key.slice(SERIES_PREFIX.length)))
    .filter((id) => Number.isInteger(id))
}

const PROCESSES_PREFIX = "processes:"
const HOST_PREFIX = "host:"
/** An agent id is a uuid: fixed length, no colon, so what follows it is the host. */
const AGENT_ID_LENGTH = 36

export interface HostRef {
  agentId: string
  host: string
}

function refAfter(key: string, prefix: string): HostRef | null {
  if (!key.startsWith(prefix)) return null
  const rest = key.slice(prefix.length)
  if (rest.charAt(AGENT_ID_LENGTH) !== ":") return null
  return { agentId: rest.slice(0, AGENT_ID_LENGTH), host: rest.slice(AGENT_ID_LENGTH + 1) }
}

export function processesKey(ref: HostRef): string {
  return `${PROCESSES_PREFIX}${ref.agentId}:${ref.host}`
}

/** The hosts whose process table is ticked. */
export function tickedProcesses(ticked: readonly string[]): HostRef[] {
  return ticked.map((key) => refAfter(key, PROCESSES_PREFIX)).filter((ref): ref is HostRef => ref !== null)
}

/** The host a tree key names, when it names a host. */
export function hostOfKey(key: string | null): HostRef | null {
  return key === null ? null : refAfter(key, HOST_PREFIX)
}

export function catalogTree(catalog: MetricsCatalog | undefined): TreeNodes {
  return (catalog?.agents ?? []).map((agent) => ({
    key: `agent:${agent.agent_id}`,
    label: agent.name,
    icon: "sensors",
    children: agent.hosts.map((host) => ({
      key: `${HOST_PREFIX}${agent.agent_id}:${host.host}`,
      label: host.host,
      icon: "dns",
      children: [
        ...host.metrics.map((metric) => ({
        key: `metric:${agent.agent_id}:${host.host}:${metric.metric}`,
        label: metric.metric,
        icon: "show_chart",
        children: metric.series.map((series) => ({
          key: seriesKey(series.id),
          label: series.label ? `${series.field} ${series.label}` : series.field,
          caption: series.unit,
        })),
      })),
        ...(host.processes
          ? [{ key: processesKey({ agentId: agent.agent_id, host: host.host }), label: "processes", icon: "list" }]
          : []),
      ],
    })),
  }))
}
