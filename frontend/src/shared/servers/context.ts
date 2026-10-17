import {
  ACTIVE_SERVER_KEY, LEGACY_SERVER_KEY, PROFILES_KEY,
  normalizeServerUrl, parseProfile, parseProfiles, scopedServerKey,
} from "./profiles"
import type { ServerProfile } from "./profiles"
import { t } from "@/shared/i18n"

interface ServerContext {
  active: ServerProfile
  defaultServer: ServerProfile
  legacyUrl: string
}

let context: ServerContext | null = null

function read(storage: Storage, key: string): string | null {
  try { return storage.getItem(key) } catch { return null }
}

function initialize(): ServerContext {
  const configured = import.meta.env.VITE_API_URL?.trim() || window.location.origin
  const defaultServer = {
    // A getter: the context is built once, before the account's language is known.
    get name() {
      return t("shell.default_server")
    },
    url: normalizeServerUrl(new URL(configured, window.location.origin).href),
  }
  const legacyUrl = read(localStorage, LEGACY_SERVER_KEY) ?? defaultServer.url
  try { localStorage.setItem(LEGACY_SERVER_KEY, legacyUrl) } catch { /* Storage may be unavailable. */ }
  let remembered: ServerProfile | null = null
  try { remembered = parseProfile(JSON.parse(read(sessionStorage, ACTIVE_SERVER_KEY) ?? "null")) } catch { /* Use the default. */ }
  const rawRequested = new URL(window.location.href).searchParams.get("server")
  let requested: string | null = null
  try { requested = rawRequested === null ? null : normalizeServerUrl(rawRequested) } catch { /* The route will show the invalid address. */ }
  const known = [defaultServer, ...parseProfiles(read(localStorage, PROFILES_KEY))]
  const selected = known.find((profile) => profile.url === requested)
  const active = selected ?? remembered ?? defaultServer
  const rememberActive = () => {
    try { sessionStorage.setItem(ACTIVE_SERVER_KEY, JSON.stringify(active)) } catch { /* Navigation still carries the choice. */ }
  }
  rememberActive()
  // Back/forward cache can restore this document without running its setup.
  // Its next reload must still choose the server actually visible in the tab.
  window.addEventListener("pageshow", (event) => { if (event.persisted) rememberActive() })
  return { active, defaultServer, legacyUrl }
}

/** Frozen for this document: changing profiles must never retarget a live request. */
export function serverContext(): ServerContext {
  context ??= initialize()
  return context
}

export function serverStorageKey(key: string): string {
  const { active, legacyUrl } = serverContext()
  return scopedServerKey(key, active.url, legacyUrl)
}

export function serverUrl(path: string): string {
  return serverContext().active.url + "/" + path.replace(/^\/+/, "")
}
