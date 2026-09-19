import { FitAddon } from "@xterm/addon-fit"
import { Terminal } from "@xterm/xterm"
import { computed, effectScope, markRaw, ref, watch } from "vue"
import type { Raw } from "vue"

import { serverUrl } from "@/shared/servers/context"
import { useAuthStore } from "@/stores/auth"

import { openTerminalLink } from "./terminalLink"
import type { LinkState, TerminalLink } from "./terminalLink"
import { afterClosing, nextOrdinal } from "./terminals"
import type { OpenTerminal } from "./terminals"

/**
 * The terminals open in this browser tab, and the one in front (D149).
 *
 * Module-level, like the panel they are shown in: the panel shows one tool at
 * a time, and switching to Services and back must not end a shell. So a
 * terminal's screen — xterm's own object — lives here with its socket, and a
 * view only lends it an element to draw in while it is on screen.
 */
export interface TerminalSession extends OpenTerminal {
  state: LinkState
  /** Not reactive: Vue must not wrap any of these in a proxy. */
  screen: Raw<Terminal>
  fit: Raw<FitAddon>
  link: Raw<TerminalLink> | null
}

const MONOSPACE = 'ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace'

const sessions = ref<TerminalSession[]>([])
const activeId = ref<string | null>(null)
// Not `crypto.randomUUID`, which a page served over plain HTTP to another
// machine does not have.
let opened = 0

function socketUrl(): string {
  const url = new URL(serverUrl("/api/v1/terminals"))
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:"
  return url.toString()
}

function find(id: string): TerminalSession | undefined {
  return sessions.value.find((session) => session.id === id)
}

function connect(session: TerminalSession) {
  const token = useAuthStore().token
  if (token === null) {
    session.state = {
      kind: "refused",
      code: "unauthenticated",
      message: "Sign in again to open a terminal",
      errorKind: null,
    }
    return
  }
  session.state = { kind: "connecting" }
  session.link = markRaw(
    openTerminalLink({
      url: socketUrl(),
      token,
      connectorId: session.connectorId,
      size: { cols: session.screen.cols, rows: session.screen.rows },
      onOutput: (data) => {
        session.screen.write(data)
      },
      onState: (state) => {
        // Through the list: a terminal closed meanwhile is no longer in it,
        // and nothing more is said about it.
        const shown = find(session.id)
        if (shown) shown.state = state
      },
    })
  )
}

function openOn(connectorId: string): string {
  const screen = markRaw(
    new Terminal({
      fontFamily: MONOSPACE,
      fontSize: 13,
      cursorBlink: true,
      scrollback: 5000,
    })
  )
  const fit = markRaw(new FitAddon())
  screen.loadAddon(fit)
  opened += 1
  const id = `terminal-${String(opened)}`
  sessions.value.push({
    id,
    connectorId,
    ordinal: nextOrdinal(sessions.value, connectorId),
    state: { kind: "connecting" },
    screen,
    fit,
    link: null,
  })
  const session = find(id)
  if (session === undefined) return id
  // Registered once for the screen's life, and reaching whichever socket it
  // has now: opening again replaces the socket, not the screen.
  screen.onData((data) => {
    find(id)?.link?.type(data)
  })
  screen.onBinary((data) => {
    find(id)?.link?.typeBytes(data)
  })
  screen.onResize((size) => {
    find(id)?.link?.resize(size)
  })
  connect(session)
  activeId.value = id
  return id
}

/** A new shell in the same screen, once the last one has stopped. */
function openAgain(id: string) {
  const session = find(id)
  if (session === undefined) return
  session.link?.close()
  // The old output stays above, separated, as a terminal shows a new session.
  session.screen.write("\r\n")
  connect(session)
}

function close(id: string) {
  const session = find(id)
  if (session === undefined) return
  activeId.value = afterClosing(sessions.value, id, activeId.value)
  session.link?.close()
  session.screen.dispose()
  sessions.value = sessions.value.filter((one) => one.id !== id)
}

function closeAll() {
  for (const session of [...sessions.value]) close(session.id)
}

let watchingSignIn = false

/**
 * Every terminal goes with the person who opened it: on sign-out, and when
 * another tab signs somebody else in. Watched here rather than called from
 * the sign-out, which lives in `shared` and knows no feature.
 */
function closeOnSignOut() {
  if (watchingSignIn) return
  watchingSignIn = true
  const auth = useAuthStore()
  effectScope(true).run(() => {
    watch(
      () => auth.token,
      (token, before) => {
        if (token !== before) closeAll()
      }
    )
  })
}

export function useTerminals() {
  closeOnSignOut()
  return {
    sessions: computed(() => sessions.value),
    active: computed(() => sessions.value.find((one) => one.id === activeId.value) ?? null),
    openOn,
    openAgain,
    close,
    select: (id: string) => {
      if (find(id)) activeId.value = id
    },
  }
}
