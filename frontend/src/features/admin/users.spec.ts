import { describe, expect, it } from "vitest"

import type { UserPublic } from "@/client"
import {
  emptyForm,
  formOf,
  storageLimitText,
  toCreate,
  toUpdate,
  undeletableReason,
  validate,
} from "./users"

const user: UserPublic = {
  id: "0a1b2c3d-0000-0000-0000-000000000001",
  email: "ada@example.com",
  full_name: "Ada",
  is_active: true,
  is_superuser: false,
}

describe("validate", () => {
  it("wants an address that looks like one", () => {
    expect(validate({ ...emptyForm(), email: "ada" }).email).toBeTruthy()
    expect(validate({ ...emptyForm(), email: "ada@example.com" })).toEqual({})
  })
})

describe("what is sent", () => {
  it("never sends a password: the person chooses it through their link", () => {
    expect("password" in toCreate({ ...emptyForm(), email: "a@b.co" })).toBe(false)
    expect("password" in toUpdate(formOf(user))).toBe(false)
  })

  it("sends an empty name as nothing rather than as an empty string", () => {
    expect(toCreate({ ...emptyForm(), email: "a@b.co" }).full_name).toBeNull()
  })
})

describe("the storage limit (D324)", () => {
  it("sends an empty field as null, which leaves the server's figure", () => {
    expect(toUpdate(formOf(user)).storage_quota_mb).toBeNull()
    expect(toUpdate({ ...formOf(user), storageQuotaMb: 500 }).storage_quota_mb).toBe(500)
  })

  it("refuses a negative or fractional figure", () => {
    expect(validate({ ...formOf(user), storageQuotaMb: -1 }).storageQuotaMb).toBeTruthy()
    expect(validate({ ...formOf(user), storageQuotaMb: 1.5 }).storageQuotaMb).toBeTruthy()
    expect(validate({ ...formOf(user), storageQuotaMb: 0 })).toEqual({})
  })

  it("tells the server's figure, no limit and a person's own apart in the table", () => {
    const texts = [null, 0, 250].map((n) => storageLimitText({ ...user, storage_quota_mb: n }))
    expect(new Set(texts).size).toBe(3)
    expect(texts[2]).toContain("250")
  })
})

describe("undeletableReason", () => {
  it("says why your own account has no delete", () => {
    expect(undeletableReason(user, user.id)).toBeTruthy()
  })

  it("says nothing about anybody else's", () => {
    expect(undeletableReason(user, "0a1b2c3d-0000-0000-0000-000000000002")).toBe("")
  })
})
