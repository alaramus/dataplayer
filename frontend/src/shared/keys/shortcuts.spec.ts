import { afterEach, describe, expect, it, vi } from "vitest"

import {
  isModKey,
  isShortcutKey,
  keysOf,
  keyshortcutsOf,
  mayTake,
  onMac,
  OWNS_KEYS,
  registerShortcut,
  shortcutList,
} from "./shortcuts"
import type { Press } from "./shortcuts"

function press(over: Partial<Press>): Press {
  return {
    key: "k",
    code: "KeyK",
    ctrlKey: false,
    metaKey: false,
    altKey: false,
    shiftKey: false,
    ...over,
  }
}

const cleanups: (() => void)[] = []

afterEach(() => {
  for (const cleanup of cleanups.splice(0)) cleanup()
  document.body.innerHTML = ""
})

describe("Mod+K", () => {
  it("is Ctrl+K on Windows and Linux", () => {
    expect(isModKey(press({ ctrlKey: true }), "k", false)).toBe(true)
    expect(isModKey(press({ metaKey: true }), "k", false)).toBe(false)
  })

  it("is ⌘K on a Mac, where Ctrl+K stays the system's kill-line", () => {
    expect(isModKey(press({ metaKey: true }), "k", true)).toBe(true)
    expect(isModKey(press({ ctrlKey: true }), "k", true)).toBe(false)
  })

  it("is not Mod with another modifier as well", () => {
    expect(isModKey(press({ ctrlKey: true, shiftKey: true }), "k", false)).toBe(false)
    expect(isModKey(press({ ctrlKey: true, altKey: true }), "k", false)).toBe(false)
    expect(isModKey(press({ ctrlKey: true, metaKey: true }), "k", false)).toBe(false)
  })

  it("is the same key on a Russian layout, where it types л", () => {
    expect(isModKey(press({ key: "л", ctrlKey: true }), "k", false)).toBe(true)
  })

  it("is not taken while a word is being composed", () => {
    expect(isModKey(press({ ctrlKey: true, isComposing: true }), "k", false)).toBe(false)
  })

  it("is not another letter", () => {
    expect(isModKey(press({ key: "j", code: "KeyJ", ctrlKey: true }), "k", false)).toBe(false)
  })

  it("is written as the platform writes it", () => {
    expect(keysOf("k", false)).toBe("Ctrl + K")
    expect(keysOf("k", true)).toBe("⌘ + K")
    expect(keyshortcutsOf("k", false)).toBe("Control+K")
    expect(keyshortcutsOf("k", true)).toBe("Meta+K")
  })

  it("tells a Mac by its platform", () => {
    expect(onMac("MacIntel")).toBe(true)
    expect(onMac("Win32")).toBe(false)
    expect(onMac("Linux x86_64")).toBe(false)
  })
})

describe("a function key", () => {
  it("is pressed alone, on every platform", () => {
    expect(isShortcutKey(press({ key: "F1", code: "F1" }), "F1", false)).toBe(true)
    expect(isShortcutKey(press({ key: "F1", code: "F1" }), "F1", true)).toBe(true)
  })

  it("is not the same key with a modifier, nor another function key", () => {
    expect(isShortcutKey(press({ key: "F1", code: "F1", ctrlKey: true }), "F1", false)).toBe(false)
    expect(isShortcutKey(press({ key: "F1", code: "F1", shiftKey: true }), "F1", false)).toBe(false)
    expect(isShortcutKey(press({ key: "F2", code: "F2" }), "F1", false)).toBe(false)
  })

  it("leaves a letter to Mod", () => {
    expect(isShortcutKey(press({ ctrlKey: true }), "k", false)).toBe(true)
    expect(isShortcutKey(press({}), "k", false)).toBe(false)
  })

  it("is written as itself", () => {
    expect(keysOf("F1", false)).toBe("F1")
    expect(keysOf("F1", true)).toBe("F1")
    expect(keyshortcutsOf("F1", true)).toBe("F1")
  })
})

describe("where a shortcut may be taken", () => {
  it("is anywhere but a terminal and behind a modal dialog", () => {
    expect(mayTake({ ownsKeys: false, dialogOpen: false })).toBe(true)
    expect(mayTake({ ownsKeys: true, dialogOpen: false })).toBe(false)
    expect(mayTake({ ownsKeys: false, dialogOpen: true })).toBe(false)
  })
})

describe("the registry", () => {
  function keydown(target: EventTarget, init: KeyboardEventInit) {
    const event = new KeyboardEvent("keydown", { bubbles: true, cancelable: true, ...init })
    target.dispatchEvent(event)
    return event
  }

  it("lists what is registered, and stops listing it once it goes", () => {
    const run = vi.fn()
    const unregister = registerShortcut({ id: "search", key: "k", action: "Search everything", run })
    expect(shortcutList.value).toEqual([{ keys: "Ctrl + K", action: "Search everything" }])
    unregister()
    expect(shortcutList.value).toEqual([])
  })

  it("lists Mod and a letter before a function key, whoever registered first", () => {
    cleanups.push(registerShortcut({ id: "help", key: "F1", action: "Help", run: vi.fn() }))
    cleanups.push(registerShortcut({ id: "search", key: "k", action: "Search", run: vi.fn() }))
    expect(shortcutList.value.map((one) => one.keys)).toEqual(["Ctrl + K", "F1"])
  })

  it("runs on Ctrl+K anywhere and keeps the browser's own Mod+K from it", () => {
    const run = vi.fn()
    cleanups.push(registerShortcut({ id: "search", key: "k", action: "Search", run }))
    const field = document.createElement("textarea")
    document.body.append(field)
    const event = keydown(field, { key: "k", code: "KeyK", ctrlKey: true })
    expect(run).toHaveBeenCalledOnce()
    expect(event.defaultPrevented).toBe(true)
  })

  it("leaves a terminal's keys to the terminal", () => {
    const run = vi.fn()
    cleanups.push(registerShortcut({ id: "search", key: "k", action: "Search", run }))
    const terminal = document.createElement("div")
    terminal.setAttribute(OWNS_KEYS, "")
    const helper = document.createElement("textarea")
    terminal.append(helper)
    document.body.append(terminal)
    const event = keydown(helper, { key: "k", code: "KeyK", ctrlKey: true })
    expect(run).not.toHaveBeenCalled()
    expect(event.defaultPrevented).toBe(false)
  })

  it("is not taken while a modal dialog is open", () => {
    const run = vi.fn()
    cleanups.push(registerShortcut({ id: "search", key: "k", action: "Search", run }))
    const dialog = document.createElement("div")
    dialog.setAttribute("aria-modal", "true")
    document.body.append(dialog)
    keydown(document.body, { key: "k", code: "KeyK", ctrlKey: true })
    expect(run).not.toHaveBeenCalled()
  })

  it("hears nothing once nothing is registered", () => {
    const run = vi.fn()
    registerShortcut({ id: "search", key: "k", action: "Search", run })()
    keydown(document.body, { key: "k", code: "KeyK", ctrlKey: true })
    expect(run).not.toHaveBeenCalled()
  })
})
