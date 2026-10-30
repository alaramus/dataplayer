import { describe, expect, it } from "vitest"

import { newPasswordErrors, requiredCredentialErrors } from "./validation"

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

describe("a password being chosen", () => {
  it("wants it long enough and typed the same twice", () => {
    expect(newPasswordErrors("short", "short").password).toBeTruthy()
    expect(newPasswordErrors("long-enough", "long-enougH").repeat).toBeTruthy()
    expect(newPasswordErrors("long-enough", "long-enough")).toEqual({ password: "", repeat: "" })
  })
})
