import { describe, expect, it } from "vitest"

import type { UserPublic } from "@/client"
import {
  emptyForm,
  formOf,
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
    const form = { ...emptyForm(), email: "ada", password: "longenough" }
    expect(validate(form, true).email).toBeTruthy()
  })

  it("wants a password for a new account", () => {
    const form = { ...emptyForm(), email: "ada@example.com" }
    expect(validate(form, true).password).toBeTruthy()
  })

  it("lets an existing account keep the password it has", () => {
    const form = { ...emptyForm(), email: "ada@example.com" }
    expect(validate(form, false)).toEqual({})
  })

  it("refuses a password too short to be accepted", () => {
    const form = { ...emptyForm(), email: "ada@example.com", password: "short" }
    expect(validate(form, false).password).toBeTruthy()
  })
})

describe("what is sent", () => {
  it("never carries a password back from the server into the form", () => {
    expect(formOf(user).password).toBe("")
  })

  it("sends an empty name as nothing rather than as an empty string", () => {
    const body = toCreate({ ...emptyForm(), email: "a@b.co", password: "longenough" })
    expect(body.full_name).toBeNull()
  })

  it("leaves the password out when the box was not filled in", () => {
    // An empty box means "keep the stored one". Sending it would set a
    // password of no characters.
    expect("password" in toUpdate(formOf(user))).toBe(false)
  })

  it("sends the password when one was typed", () => {
    expect(toUpdate({ ...formOf(user), password: "a-new-secret" }).password).toBe(
      "a-new-secret"
    )
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
