import { AxiosError, AxiosHeaders } from "axios"
import { describe, expect, it } from "vitest"

import { fieldErrorsFrom, messageOf } from "./errors"

function axiosError(status: number, data: unknown): AxiosError {
  const error = new AxiosError("Request failed")
  error.response = {
    status,
    statusText: "",
    headers: {},
    config: { headers: new AxiosHeaders() },
    data,
  }
  return error
}

describe("messageOf", () => {
  it("reads the message the backend put in detail", () => {
    const cause = axiosError(400, { detail: { kind: "conflict", message: "Name is taken" } })

    expect(messageOf(cause, "fallback")).toBe("Name is taken")
  })

  // FastAPI answers a validation failure with a list, not an object.
  it("reads the first message of a validation list", () => {
    const cause = axiosError(422, { detail: [{ loc: ["body"], msg: "too large", type: "value" }] })

    expect(messageOf(cause, "fallback")).toBe("too large")
  })

  it("falls back when the response carries no usable detail", () => {
    expect(messageOf(axiosError(500, {}), "fallback")).toBe("fallback")
    expect(messageOf(axiosError(500, { detail: "plain" }), "fallback")).toBe("fallback")
  })

  it("falls back for anything that is not an axios error", () => {
    expect(messageOf(new Error("boom"), "fallback")).toBe("fallback")
    expect(messageOf(null, "fallback")).toBe("fallback")
  })
})

describe("fieldErrorsFrom", () => {
  it("returns the list from a 422", () => {
    const detail = [{ loc: ["body", "options", "host"], msg: "required", type: "missing" }]

    expect(fieldErrorsFrom(axiosError(422, { detail }))).toEqual(detail)
  })

  // A 400 carrying a list is not a field-level failure; treating it as one
  // would silently swallow the message instead of showing it.
  it("returns null for any other status", () => {
    expect(fieldErrorsFrom(axiosError(400, { detail: [] }))).toBeNull()
  })

  it("returns null when a 422 carries an object rather than a list", () => {
    expect(fieldErrorsFrom(axiosError(422, { detail: { message: "no" } }))).toBeNull()
  })
})
