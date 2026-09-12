import { describe, expect, it } from "vitest"

import { requiredCredentialErrors } from "./validation"

describe("required sign-in credentials", () => {
  it("identifies both missing fields", () => {
    expect(requiredCredentialErrors("", "")).toEqual({
      username: "Email is required", password: "Password is required",
    })
  })

  it("rejects whitespace-only email without trimming a password", () => {
    expect(requiredCredentialErrors("  ", " ")).toEqual({
      username: "Email is required", password: "",
    })
  })

  it("leaves credential validity to sign-in once both fields are present", () => {
    expect(requiredCredentialErrors("person@example.com", "password")).toEqual({
      username: "", password: "",
    })
  })
})
