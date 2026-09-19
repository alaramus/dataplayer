import { describe, expect, it } from "vitest"

import { buildStart, canStart, passwordProblem } from "./starts"
import type { StartForm } from "./starts"

function form(over: Partial<StartForm> = {}): StartForm {
  return {
    mode: "chosen",
    name: "orders",
    user: "reader",
    database: "shop",
    port: 0,
    wantsPassword: true,
    password: "",
    signIn: "password",
    keyId: "",
    sampleData: true,
    choosable: ["user", "password", "database"],
    offersSampleData: true,
    optionalPassword: false,
    keySignIn: false,
    ...over,
  }
}

describe("what a filled-in start form means", () => {
  it("says nothing at all when it is automatic", () => {
    // Not even the name: somebody who has not been asked for one has not got
    // one in mind, and every other answer is the server's.
    expect(buildStart(form({ mode: "automatic" }))).toEqual({ mode: "automatic" })
  })

  it("carries what was chosen, trimmed", () => {
    expect(buildStart(form({ name: "  orders  ", user: " reader " }))).toEqual({
      mode: "chosen",
      name: "orders",
      user: "reader",
      database: "shop",
      port: 0,
      password: { kind: "generated" },
      sample_data: true,
    })
  })

  it("leaves out a field the person left empty", () => {
    const built = buildStart(form({ user: "   ", database: "" }))

    expect(built).toMatchObject({ user: null, database: null })
  })

  it("does not send a value for a slot the template did not open", () => {
    // A Redis server has no role and no named database; the server refuses a
    // request that names one, and a form that sends what will be refused is a
    // form that lies.
    const built = buildStart(form({ choosable: [] }))

    expect(built).toMatchObject({ user: null, database: null })
  })

  it("does not ask for sample data where the source has none", () => {
    expect(buildStart(form({ offersSampleData: false }))).toMatchObject({
      sample_data: false,
    })
  })
})

describe("which port it asks for", () => {
  it("sends the number somebody meant", () => {
    expect(buildStart(form({ port: 5433 }))).toMatchObject({ port: 5433 })
  })

  it("asks the runtime to pick when the field says nothing usable", () => {
    // A number field reports what has been typed so far, and half-typed is a
    // real state: zero is what the server takes for "pick one".
    for (const written of [0, -1, 70000, 1.5, Number.NaN]) {
      expect(buildStart(form({ port: written }))).toMatchObject({ port: 0 })
    }
  })
})

describe("how the password is decided", () => {
  it("has the server make one up when the field is empty", () => {
    // The same thing the automatic start gives, rather than a service with no
    // password at all — which is a different request.
    expect(buildStart(form())).toMatchObject({ password: { kind: "generated" } })
  })

  it("sends the one that was typed", () => {
    expect(buildStart(form({ password: "correct-horse-9" }))).toMatchObject({
      password: { kind: "chosen", value: "correct-horse-9" },
    })
  })

  it("asks for none only where the template runs without one", () => {
    expect(
      buildStart(form({ optionalPassword: true, wantsPassword: false }))
    ).toMatchObject({ password: { kind: "none" } })
    // A PostgreSQL never offers the choice, so an unticked box left over from
    // one that did must not turn into a request the server would refuse.
    expect(
      buildStart(form({ optionalPassword: false, wantsPassword: false }))
    ).toMatchObject({ password: { kind: "generated" } })
  })

  it("does not send one for a template that has no password to name", () => {
    expect(
      buildStart(form({ choosable: [], password: "correct-horse-9" }))
    ).toMatchObject({ password: { kind: "generated" } })
  })
})

describe("what is wrong with the password", () => {
  it("says nothing about an empty one, which is a request rather than a gap", () => {
    expect(passwordProblem(form())).toBeNull()
  })

  it("names the rule for one that would not survive where it goes", () => {
    // It becomes an environment variable, a command-line argument and part of
    // a connection string.
    expect(passwordProblem(form({ password: "short" }))).not.toBeNull()
    expect(passwordProblem(form({ password: "with space" }))).not.toBeNull()
    expect(passwordProblem(form({ password: "correct-horse-9" }))).toBeNull()
  })

  it("has nothing to say where no password was asked for", () => {
    expect(
      passwordProblem(
        form({ optionalPassword: true, wantsPassword: false, password: "short" })
      )
    ).toBeNull()
  })
})

describe("whether the form can be sent", () => {
  it("needs a name only when one was asked for", () => {
    expect(canStart(form({ mode: "automatic", name: "" }))).toBe(true)
    expect(canStart(form({ name: "" }))).toBe(false)
    expect(canStart(form({ name: "  " }))).toBe(false)
    expect(canStart(form({ name: "orders" }))).toBe(true)
  })

  it("will not send a password the server would refuse", () => {
    expect(canStart(form({ password: "short" }))).toBe(false)
    expect(canStart(form({ password: "correct-horse-9" }))).toBe(true)
  })
})

describe("a server signed into with one of the person's keys (D154)", () => {
  const ssh = { choosable: ["user", "password"], keySignIn: true, signIn: "key" as const }

  it("sends the key rather than any password", () => {
    const built = buildStart(form({ ...ssh, keyId: "key-1", password: "typed-but-unused" }))

    expect(built).toMatchObject({ password: { kind: "key", key_id: "key-1" } })
  })

  it("cannot be sent until a key is chosen", () => {
    expect(canStart(form({ ...ssh, keyId: "" }))).toBe(false)
    expect(canStart(form({ ...ssh, keyId: "key-1" }))).toBe(true)
  })

  it("does not judge a password nobody will use", () => {
    expect(passwordProblem(form({ ...ssh, keyId: "key-1", password: "a b" }))).toBeNull()
  })

  it("is a password again for a template that takes no key", () => {
    const built = buildStart(form({ signIn: "key", keyId: "key-1", keySignIn: false }))

    expect(built).toMatchObject({ password: { kind: "generated" } })
  })
})
