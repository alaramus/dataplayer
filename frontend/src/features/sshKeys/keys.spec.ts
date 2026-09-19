import { describe, expect, it } from "vitest"

import type { SshKeyPublic } from "@/client"
import type { FieldSpec } from "@/shared/SchemaForm/jsonSchema"

import {
  keyState,
  keyUsedBy,
  passphraseModeLabel,
  shortFingerprint,
  unlockOptions,
  withKeyChoices,
} from "./keys"

function key(overrides: Partial<SshKeyPublic> = {}): SshKeyPublic {
  return {
    id: "k1",
    name: "deploy",
    algorithm: "ssh-ed25519",
    public_key: "ssh-ed25519 AAAA dataplayer",
    fingerprint: "SHA256:abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
    passphrase_mode: "none",
    unlocked_until: null,
    created_at: null,
    used_by: [],
    ...overrides,
  }
}

function field(overrides: Partial<FieldSpec> = {}): FieldSpec {
  return { name: "key_id", label: "Key", kind: "text", required: true, group: "general", ...overrides }
}

describe("how long a passphrase is held", () => {
  it("offers the server's three spans, shortest first", () => {
    expect(unlockOptions().map((option) => option.value)).toEqual([15, 60, 480])
    expect(unlockOptions().map((option) => option.label)).toEqual(["15 minutes", "1 hour", "8 hours"])
  })
})

describe("what a key says about itself", () => {
  it("names each way a passphrase is kept", () => {
    expect(passphraseModeLabel("none")).toBe("No passphrase")
    expect(passphraseModeLabel("stored")).toBe("Passphrase kept")
    expect(passphraseModeLabel("ask")).toBe("Asks for its passphrase")
  })

  it("has a state only when it asks, and says whether it is open", () => {
    expect(keyState(key())).toBeNull()
    expect(keyState(key({ passphrase_mode: "ask" }))).toEqual({ text: "Locked", open: false })
    const open = keyState(key({ passphrase_mode: "ask", unlocked_until: "2026-09-19T12:30:00Z" }))
    expect(open?.open).toBe(true)
    expect(open?.text).toMatch(/^Unlocked until /)
  })

  it("shows the tail of a fingerprint, which is what is compared by eye", () => {
    expect(shortFingerprint("SHA256:abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG")).toBe("…56789ABCDEFG")
    expect(shortFingerprint("SHA256:short")).toBe("short")
  })
})

describe("choosing a key in a connection", () => {
  it("turns the field that holds a key into a choice of the owner's keys", () => {
    const [chosen] = withKeyChoices([field({ purpose: "ssh-key" })], [key(), key({ id: "k2", name: "laptop" })])

    expect(chosen?.kind).toBe("select")
    expect(chosen?.choices?.map((choice) => choice.value)).toEqual(["k1", "k2"])
    expect(chosen?.choices?.[1]?.label).toContain("laptop")
  })

  it("leaves every other field as it was", () => {
    const host = field({ name: "host", purpose: undefined })

    expect(withKeyChoices([host], [key()])).toEqual([host])
  })
})

describe("the key a connection signs in with", () => {
  it("is the one whose uses name the connection", () => {
    const used = key({ id: "k2", used_by: [{ id: "c1", name: "prod" }] })

    expect(keyUsedBy([key(), used], "c1")?.id).toBe("k2")
  })

  it("is none when no key of this person's names it", () => {
    expect(keyUsedBy([key()], "c1")).toBeNull()
  })
})
