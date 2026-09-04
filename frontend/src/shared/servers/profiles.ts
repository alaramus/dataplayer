export interface ServerProfile {
  name: string
  url: string
}

export const PROFILES_KEY = "dataplayer:servers:v1"
export const ACTIVE_SERVER_KEY = "dataplayer:active-server:v1"
export const LEGACY_SERVER_KEY = "dataplayer:legacy-server:v1"

export function normalizeServerUrl(value: string): string {
  const text = value.trim()
  if (!text || /[\\\s]/u.test(text)) throw new Error("Enter a full HTTP or HTTPS server URL.")
  let url: URL
  try { url = new URL(text) } catch {
    throw new Error("Enter a full URL, such as https://data.example.com.")
  }
  if (!["http:", "https:"].includes(url.protocol) || !url.hostname) {
    throw new Error("Use an HTTP or HTTPS server URL.")
  }
  if (url.username || url.password || text.includes("?") || text.includes("#")) {
    throw new Error("The server URL must not contain credentials, a query or a fragment.")
  }
  return url.href.replace(/\/+$/u, "")
}

export function parseProfile(value: unknown): ServerProfile | null {
  if (value === null || typeof value !== "object") return null
  const candidate = value as Partial<ServerProfile>
  if (typeof candidate.name !== "string" || typeof candidate.url !== "string") return null
  const name = candidate.name.trim()
  if (!name || name.length > 100) return null
  try { return { name, url: normalizeServerUrl(candidate.url) } } catch { return null }
}

export function parseProfiles(raw: string | null): ServerProfile[] {
  try {
    const parsed: unknown = JSON.parse(raw ?? "[]")
    if (!Array.isArray(parsed)) return []
    const profiles = new Map<string, ServerProfile>()
    for (const value of parsed.slice(0, 50)) {
      const profile = parseProfile(value)
      if (profile !== null) profiles.set(profile.url, profile)
    }
    return [...profiles.values()]
  } catch { return [] }
}

export function scopedServerKey(key: string, url: string, legacyUrl: string): string {
  return url === legacyUrl ? key : `dataplayer:server:${encodeURIComponent(url)}:${key}`
}

/** Navigation stays on this frontend; only the selected backend changes. */
export function safeLocalPath(value: unknown): string | null {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//") || /[\\\s]/u.test(value)) return null
  const parsed = new URL(value, "https://frontend.invalid")
  return parsed.origin === "https://frontend.invalid" && !parsed.pathname.startsWith("//")
    ? parsed.pathname + parsed.search + parsed.hash
    : null
}

/** A legacy share belongs to the configured server, not the last selected one. */
export function routeServerTarget(requested: unknown, shared: boolean, activeUrl: string, defaultUrl: string): string | null {
  if (requested === undefined && !shared) return null
  const raw = requested === undefined ? defaultUrl : typeof requested === "string" ? requested : ""
  try {
    const url = normalizeServerUrl(raw)
    return url === activeUrl ? null : url
  } catch { return raw }
}

export function serverNavigation(url: string, next = "/"): string {
  const local = safeLocalPath(next)
  if (local === null) throw new Error("Invalid destination")
  const destination = new URL(local, "https://frontend.invalid")
  destination.searchParams.set("server", normalizeServerUrl(url))
  return destination.pathname + destination.search + destination.hash
}
