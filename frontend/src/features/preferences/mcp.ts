/**
 * What a client outside DataPlayer is configured with to reach `/mcp` (D357).
 * Plain functions, so the text a person copies is tested without a screen.
 * Each client's own syntax, as its documentation gave it in November 2026.
 */

/** The spans a token may be made to last, as the server accepts them (D358). */
export const EXPIRY_DAYS = [7, 30, 90, 365] as const
export type ExpiryDays = (typeof EXPIRY_DAYS)[number]

/** The name a client lists the server under. */
const SERVER_NAME = "dataplayer"

/** Where the snippet goes: a terminal, or a file the client reads. */
export type ClientPlace = { kind: "terminal" } | { kind: "file"; file: string }

export interface McpClient {
  id: string
  /** A product's name, the same in every language. */
  label: string
  place: ClientPlace
  snippet: (address: string, token: string) => string
}

function bearer(token: string): string {
  return `Bearer ${token}`
}

function json(value: unknown): string {
  return JSON.stringify(value, null, 2)
}

/** Claude Code's one line, which adds the server for the current project. */
export function claudeCommand(address: string, token: string): string {
  return `claude mcp add --transport http ${SERVER_NAME} ${address} --header "Authorization: ${bearer(token)}"`
}

/** The `mcpServers` shape Cursor and most other clients read. */
export function clientJson(address: string, token: string): string {
  return json({ mcpServers: { [SERVER_NAME]: { url: address, headers: { Authorization: bearer(token) } } } })
}

export const MCP_CLIENTS: readonly McpClient[] = [
  { id: "claude-code", label: "Claude Code", place: { kind: "terminal" }, snippet: claudeCommand },
  {
    id: "codex",
    label: "Codex",
    place: { kind: "file", file: "~/.codex/config.toml" },
    snippet: (address, token) =>
      [
        `[mcp_servers.${SERVER_NAME}]`,
        `url = ${JSON.stringify(address)}`,
        `http_headers = { "Authorization" = ${JSON.stringify(bearer(token))} }`,
      ].join("\n"),
  },
  {
    id: "gemini",
    label: "Gemini CLI",
    place: { kind: "terminal" },
    snippet: (address, token) =>
      `gemini mcp add --transport http --header "Authorization: ${bearer(token)}" ${SERVER_NAME} ${address}`,
  },
  {
    id: "kimi",
    label: "Kimi Code CLI",
    place: { kind: "terminal" },
    snippet: (address, token) =>
      `kimi mcp add --transport http --header "Authorization: ${bearer(token)}" ${SERVER_NAME} ${address}`,
  },
  {
    id: "cursor",
    label: "Cursor",
    place: { kind: "file", file: "~/.cursor/mcp.json" },
    snippet: clientJson,
  },
  {
    id: "vscode",
    label: "VS Code",
    place: { kind: "file", file: ".vscode/mcp.json" },
    // `servers`, not `mcpServers`: VS Code ignores the latter.
    snippet: (address, token) =>
      json({ servers: { [SERVER_NAME]: { type: "http", url: address, headers: { Authorization: bearer(token) } } } }),
  },
  {
    id: "opencode",
    label: "opencode",
    place: { kind: "file", file: "opencode.json" },
    // OAuth off: opencode would otherwise try to discover a sign-in first.
    snippet: (address, token) =>
      json({
        $schema: "https://opencode.ai/config.json",
        mcp: {
          [SERVER_NAME]: {
            type: "remote",
            url: address,
            enabled: true,
            oauth: false,
            headers: { Authorization: bearer(token) },
          },
        },
      }),
  },
]

/** Whether a token can no longer be used, judged at `now`. */
export function isExpired(expiresAt: string | null | undefined, now: Date = new Date()): boolean {
  return expiresAt != null && new Date(expiresAt).getTime() <= now.getTime()
}
