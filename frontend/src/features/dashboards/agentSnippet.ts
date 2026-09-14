/**
 * The Compose file an agent is started with, written for one key (D128).
 *
 * The agent reads the host through read-only mounts and the host's process and
 * network namespaces, so what it reports is the machine and not its own
 * container. `/:/host` is plain `ro`: Docker Desktop refuses `rslave`.
 */

export const AGENT_IMAGE = "alaramus/dataplayer-monitor-agent:latest"

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "::1", "[::1]"])

export interface SnippetRequest {
  key: string
  port: number
  /** The machine this server runs on, as the browser reaches it. */
  serverHost: string
  /** What the agent's host is called in every chart; empty for its own name. */
  hostname: string
}

function quoted(text: string): string {
  return JSON.stringify(text)
}

export function composeSnippet(request: SnippetRequest): string {
  const hostname = request.hostname.trim()
  // With the host's network, the machine this server runs on is itself.
  const server = LOCAL_HOSTS.has(request.serverHost) ? "127.0.0.1" : request.serverHost
  return [
    "services:",
    "  dpm-agent:",
    `    image: ${AGENT_IMAGE}`,
    "    restart: unless-stopped",
    "    pid: host",
    "    network_mode: host",
    "    environment:",
    `      DPM_SERVER: ${quoted(`${server}:${String(request.port)}`)}`,
    `      DPM_KEY: ${quoted(request.key)}`,
    ...(hostname === "" ? [] : [`      DPM_HOSTNAME: ${quoted(hostname)}`]),
    "      DPM_PROC: /host/proc",
    "      DPM_SYS: /host/sys",
    "      DPM_ROOTFS: /host",
    "    volumes:",
    "      - /:/host:ro",
    "      - /var/run/docker.sock:/var/run/docker.sock:ro",
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
