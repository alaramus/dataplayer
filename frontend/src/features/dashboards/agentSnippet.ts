/**
 * The Compose file an agent is started with, written for one key.
 *
 * `iftop` is left out: version 1.14.0 crashes on it in a container without
 * traffic and restarts every half minute (D130). The host name is fixed,
 * because a container id would be a new host, and new series, on every
 * recreation.
 */

export const AGENT_ACTIONS = "tcp:30,disk:30[/],ps:30,df:30[/],net:30,memory:30,cpu:30"

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "::1", "[::1]"])

export interface SnippetRequest {
  key: string
  port: number
  /** The machine this server runs on, as the browser reaches it. */
  serverHost: string
  /** What the agent's host is called in every chart. */
  hostname: string
}

export function composeSnippet(request: SnippetRequest): string {
  const hostname = request.hostname.trim().replace(/[^A-Za-z0-9.-]+/g, "-") || "monitored-host"
  // On the machine this server runs on, the agent finds it by itself.
  const address = LOCAL_HOSTS.has(request.serverHost)
    ? "      # IP: address of the DataPlayer server, when the agent runs elsewhere"
    : `      IP: ${request.serverHost}`
  return [
    "services:",
    "  sys_monitor_agent:",
    "    image: daniylx/sys_monitor_agent:latest",
    `    hostname: ${hostname}`,
    "    environment:",
    `      API_KEY: ${request.key}`,
    `      PORT: "${String(request.port)}"`,
    address,
    `      ACTIONS: "${AGENT_ACTIONS}"`,
    "    restart: unless-stopped",
    "",
  ].join("\n")
}

/** When an agent was last heard from, as a person reads it. */
export function lastHeardWording(lastHeardAt: string | null | undefined, nowMs: number): string {
  if (lastHeardAt === null || lastHeardAt === undefined) return "Never"
  const seconds = Math.max(0, Math.round((nowMs - Date.parse(lastHeardAt)) / 1000))
  if (seconds < 60) return `${String(seconds)} s ago`
  if (seconds < 3600) return `${String(Math.floor(seconds / 60))} min ago`
  if (seconds < 86400) return `${String(Math.floor(seconds / 3600))} h ago`
  return `${String(Math.floor(seconds / 86400))} d ago`
}
