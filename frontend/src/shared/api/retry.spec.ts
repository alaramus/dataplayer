import { AxiosError, AxiosHeaders } from "axios"
import { describe, expect, it } from "vitest"

import { isSettledRefusal, shouldRetry } from "./retry"

function answeredWith(status: number): AxiosError {
  const error = new AxiosError("refused")
  error.response = {
    status,
    statusText: "",
    data: {},
    headers: {},
    config: { headers: new AxiosHeaders() },
  }
  return error
}

describe("whether a failed request is worth making again", () => {
  it("does not ask again when the server refused the request itself", () => {
    // The case this was written for: opening a file the source says is
    // binary. Three retries turned an immediate answer into a five-second
    // wait for the same sentence.
    expect(isSettledRefusal(answeredWith(400))).toBe(true)
    expect(isSettledRefusal(answeredWith(404))).toBe(true)
    expect(isSettledRefusal(answeredWith(422))).toBe(true)
    expect(isSettledRefusal(answeredWith(501))).toBe(false)
  })

  it("asks again about the two refusals that are about the moment", () => {
    expect(isSettledRefusal(answeredWith(408))).toBe(false)
    expect(isSettledRefusal(answeredWith(429))).toBe(false)
  })

  it("asks again when the server broke rather than refused", () => {
    expect(isSettledRefusal(answeredWith(500))).toBe(false)
    expect(isSettledRefusal(answeredWith(503))).toBe(false)
  })

  it("asks again when nothing answered at all", () => {
    // A request that never arrived says nothing about itself, so the moment
    // is the only thing that could have been wrong with it.
    expect(isSettledRefusal(new AxiosError("Network Error"))).toBe(false)
    expect(isSettledRefusal(new Error("boom"))).toBe(false)
  })

  it("stops at the ceiling for failures it does retry", () => {
    expect(shouldRetry(0, answeredWith(503), 3)).toBe(true)
    expect(shouldRetry(2, answeredWith(503), 3)).toBe(true)
    expect(shouldRetry(3, answeredWith(503), 3)).toBe(false)
  })

  it("does not retry a settled refusal even on the first failure", () => {
    expect(shouldRetry(0, answeredWith(422), 3)).toBe(false)
  })
})
