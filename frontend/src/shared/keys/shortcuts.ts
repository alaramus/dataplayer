import { computed, shallowReactive } from "vue"

/**
 * The application's keyboard shortcuts: one registry, one listener (D205).
 *
 * A screen registers what it answers to for as long as it is mounted, and the
 * workspace's empty scene lists what is registered — so a key that is drawn
 * there is a key that works, and one that is not registered is not promised.
 *
 * Mod is Ctrl on Windows and Linux and ⌘ on a Mac. On a Mac Ctrl+K is the
 * system's kill-line and stays so: the SQL editor, CodeMirror, binds it there.
 */
export interface Shortcut {
  id: string
  /** The letter pressed with Mod, lower case. */
  key: string
  /** What it does, in the words the scene lists it with. */
  action: string
  run: () => void
}

/** What a key press is, as far as the rule is concerned. */
export interface Press {
  key: string
  code: string
  ctrlKey: boolean
  metaKey: boolean
  altKey: boolean
  shiftKey: boolean
  isComposing?: boolean
}

/** Where the focus is when the key is pressed. */
export interface Where {
  /** In something that owns every key, a terminal (D148). */
  ownsKeys: boolean
  /** A modal dialog is open: nothing behind it is reachable. */
  dialogOpen: boolean
}

/** Whether this browser runs on a Mac, decided the way CodeMirror decides it. */
export function onMac(platform: string = typeof navigator === "undefined" ? "" : navigator.platform): boolean {
  return /Mac|iPhone|iPad|iPod/.test(platform)
}

/**
 * The letter pressed, whatever the layout: on a Russian keyboard K is "л",
 * and a shortcut that worked in one layout only would not be one.
 */
function letterOf(press: Press): string {
  const key = press.key.toLowerCase()
  if (/^[a-z]$/.test(key)) return key
  const code = /^Key([A-Z])$/.exec(press.code)
  return code?.[1]?.toLowerCase() ?? key
}

/** Whether a press is Mod plus this letter, and nothing else. */
export function isModKey(press: Press, letter: string, mac: boolean): boolean {
  if (press.isComposing === true || press.altKey || press.shiftKey) return false
  const mod = mac ? press.metaKey && !press.ctrlKey : press.ctrlKey && !press.metaKey
  return mod && letterOf(press) === letter
}

/** Whether the application may take a shortcut here at all. */
export function mayTake(where: Where): boolean {
  return !where.ownsKeys && !where.dialogOpen
}

/** How a shortcut is written for a person on this platform: "Ctrl + K", "⌘ + K". */
export function keysOf(letter: string, mac: boolean): string {
  return `${mac ? "⌘" : "Ctrl"} + ${letter.toUpperCase()}`
}

/** The same keys as `aria-keyshortcuts` spells them: "Control+K", "Meta+K". */
export function keyshortcutsOf(letter: string, mac: boolean): string {
  return `${mac ? "Meta" : "Control"}+${letter.toUpperCase()}`
}

/**
 * What marks an element whose keys are its own. A terminal carries it: once
 * ready it owns every key (D148), and Ctrl+K is readline's kill-line there.
 */
export const OWNS_KEYS = "data-owns-keys"

function whereOf(event: KeyboardEvent): Where {
  const target = event.target instanceof Element ? event.target : null
  return {
    ownsKeys: target?.closest(`[${OWNS_KEYS}]`) != null,
    dialogOpen: document.querySelector('[aria-modal="true"]') !== null,
  }
}

const registered = shallowReactive(new Map<string, Shortcut>())

/** Every shortcut registered now, as the scene lists them. */
export const shortcutList = computed(() =>
  [...registered.values()].map((shortcut) => ({
    keys: keysOf(shortcut.key, onMac()),
    action: shortcut.action,
  }))
)

function onKeydown(event: KeyboardEvent) {
  const mac = onMac()
  for (const shortcut of registered.values()) {
    if (!isModKey(event, shortcut.key, mac)) continue
    if (!mayTake(whereOf(event))) return
    // The browser's own Mod+K — its search bar — would take the focus away
    // from the page this was pressed in.
    event.preventDefault()
    event.stopPropagation()
    shortcut.run()
    return
  }
}

/**
 * Answer to a shortcut until the returned function is called.
 *
 * Heard in the capture phase, before an editor that binds the same keys:
 * CodeMirror would otherwise take Ctrl+K first. A terminal is let alone by
 * `mayTake`, not by the order of listeners.
 */
export function registerShortcut(shortcut: Shortcut): () => void {
  if (registered.size === 0) window.addEventListener("keydown", onKeydown, true)
  registered.set(shortcut.id, shortcut)
  return () => {
    if (registered.get(shortcut.id) !== shortcut) return
    registered.delete(shortcut.id)
    if (registered.size === 0) window.removeEventListener("keydown", onKeydown, true)
  }
}
