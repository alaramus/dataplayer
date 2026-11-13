/**
 * What a client outside DataPlayer is configured with to reach `/mcp` (D357).
 * Plain functions, so the text a person copies is tested without a screen.
 */

/** The spans a token may be made to last, as the server accepts them (D358). */
export const EXPIRY_DAYS = [7, 30, 90, 365] as const
export type ExpiryDays = (typeof EXPIRY_DAYS)[number]

/** The name a client lists the server under. */
const SERVER_NAME = "dataplayer"

/** Claude Code's one line, which adds the server for the current project. */
export function claudeCommand(address: string, token: string): string {
  return `claude mcp add --transport http ${SERVER_NAME} ${address} --header "Authorization: Bearer ${token}"`
}

/** The `mcpServers` shape Cursor, Claude Desktop and most others read. */
export function clientJson(address: string, token: string): string {
  return JSON.stringify(
    {
      mcpServers: {
        [SERVER_NAME]: {
          type: "http",
          url: address,
          headers: { Authorization: `Bearer ${token}` },
        },
      },
    },
    null,
    2
  )
}

/** Whether a token can no longer be used, judged at `now`. */
export function isExpired(expiresAt: string | null | undefined, now: Date = new Date()): boolean {
  return expiresAt != null && new Date(expiresAt).getTime() <= now.getTime()
}
