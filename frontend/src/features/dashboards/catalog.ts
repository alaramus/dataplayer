import { t } from "@/shared/i18n"
import { appIcons } from "@/shared/ui/icons"

/**
 * The catalog of what a person's agents reported, as an index and as a tree.
 *
 * A saved widget holds series ids and nothing else, so the legend, the unit and
 * the title are looked up here on every read: a host renamed on the agent side
 * shows its new name rather than one stored in the widget.
 */

import type { MetricsCatalog } from "@/client"
import { adapterIcon } from "@/features/connectors/adapters"
import type { TreeNodes } from "@/shared/ui"

export interface SeriesEntry {
  id: number
  /** The agent or the connection that reported it. */
  sourceId: string
  sourceName: string
  /** What the series is shown under: the agent's host, or the connection's name. */
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
            sourceId: agent.agent_id,
            sourceName: agent.name,
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
  for (const connector of catalog?.connectors ?? []) {
    for (const metric of connector.metrics) {
      for (const series of metric.series) {
        index.set(series.id, {
          id: series.id,
          sourceId: connector.connector_id,
          sourceName: connector.name,
          host: connector.name,
          metric: metric.metric,
          field: series.field,
          label: series.label,
          unit: series.unit,
          lastSeen: series.last_seen,
        })
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

const CONNECTOR_PREFIX = "connector:"

/** The connection a tree key names, when it names one. */
export function connectorOfKey(key: string | null): string | null {
  return key !== null && key.startsWith(CONNECTOR_PREFIX) ? key.slice(CONNECTOR_PREFIX.length) : null
}

/** The host a tree key names, when it names a host. */
export function hostOfKey(key: string | null): HostRef | null {
  return key === null ? null : refAfter(key, HOST_PREFIX)
}

function seriesNodes(series: MetricsCatalog["agents"][number]["hosts"][number]["metrics"][number]["series"]) {
  return series.map((one) => ({
    key: seriesKey(one.id),
    label: one.label ? `${one.field} ${one.label}` : one.field,
    caption: one.unit,
  }))
}

export function catalogTree(catalog: MetricsCatalog | undefined): TreeNodes {
  const connectors = (catalog?.connectors ?? []).map((connector) => ({
    key: `${CONNECTOR_PREFIX}${connector.connector_id}`,
    label: connector.name,
    icon: adapterIcon(connector.adapter_type),
    children: connector.metrics.map((metric) => ({
      key: `metric:${connector.connector_id}:${metric.metric}`,
      label: metric.metric,
      icon: appIcons.showChart,
      children: seriesNodes(metric.series),
    })),
  }))
  return [...agentNodes(catalog), ...connectors]
}

function agentNodes(catalog: MetricsCatalog | undefined): TreeNodes {
  return (catalog?.agents ?? []).map((agent) => ({
    key: `agent:${agent.agent_id}`,
    label: agent.name,
    icon: appIcons.sensors,
    children: agent.hosts.map((host) => ({
      key: `${HOST_PREFIX}${agent.agent_id}:${host.host}`,
      label: host.host,
      icon: appIcons.dns,
      children: [
        ...host.metrics.map((metric) => ({
        key: `metric:${agent.agent_id}:${host.host}:${metric.metric}`,
        label: metric.metric,
        icon: appIcons.showChart,
        children: seriesNodes(metric.series),
      })),
        ...(host.processes
          ? [{ key: processesKey({ agentId: agent.agent_id, host: host.host }), label: t("dashboards.tree.processes"), icon: appIcons.list }]
          : []),
      ],
    })),
  }))
}
