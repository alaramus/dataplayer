import { describe, expect, it } from "vitest"

import type { FieldSpec, SchemaShape } from "@/shared/SchemaForm/jsonSchema"
import { mergeParsedOptions } from "./parsedOptions"

function field(name: string, kind: FieldSpec["kind"], required = true): FieldSpec {
  return { name, label: name, kind, required, group: "general" }
}

/**
 * A source with two ways of connecting, one of which needs a secret.
 *
 * Named after nothing in particular on purpose: the rule under test is about
 * a discriminated schema and a field the schema calls a secret, and it would
 * not be a rule if it had to know which source it was looking at.
 */
const shape: SchemaShape = {
  kind: "variants",
  discriminator: {
    name: "auth_method",
    label: "Authentication",
    kind: "select",
    required: true,
    choices: [
      { value: "with_secret", label: "With secret" },
      { value: "without_secret", label: "Without secret" },
    ],
    defaultValue: "with_secret",
    group: "general",
  },
  common: [field("host", "text")],
  byVariant: {
    with_secret: [field("host", "text"), field("user", "text"), field("secret", "password")],
    without_secret: [field("host", "text"), field("user", "text")],
    // A third way, so that "the parsed variant needs no secret" and "the
    // parsed variant is a different one" are two conditions and not one.
    with_other_secret: [field("host", "text"), field("token", "password")],
  },
}

const fields = [
  field("host", "text"),
  field("user", "text"),
  field("secret", "password"),
  field("token", "password"),
  field("port", "number", false),
]

describe("what an address taken apart does to the form", () => {
  it("leaves alone what the text did not mention", () => {
    // Editing the host of an address must not blank the rest of the form.
    const merged = mergeParsedOptions({
      shape,
      fields,
      current: { host: "old", user: "ann", secret: "s3cret", port: 5432 },
      parsed: { host: "new" },
      secretsAreStored: false,
    })

    expect(merged).toEqual({
      host: "new",
      user: "ann",
      secret: "s3cret",
      token: "",
      port: 5432,
    })
  })

  it("fills in a field the form never held", () => {
    const merged = mergeParsedOptions({
      shape,
      fields,
      current: { host: "old" },
      parsed: { host: "new" },
      secretsAreStored: false,
    })

    expect(merged).toEqual({ host: "new", user: "", secret: "", token: "", port: null })
  })

  it("keeps the way of connecting when the text could not have carried the secret", () => {
    // A composed address never carries one, so taking one apart can only ever
    // answer with the variant that needs none. Believing it would switch the
    // choice under the user and hide the secret they had just typed.
    const merged = mergeParsedOptions({
      shape,
      fields,
      current: { auth_method: "with_secret", host: "old", user: "ann", secret: "s3cret" },
      parsed: { auth_method: "without_secret", host: "new", user: "ann" },
      secretsAreStored: false,
    })

    expect(merged.auth_method).toBe("with_secret")
    expect(merged.secret).toBe("s3cret")
    expect(merged.host).toBe("new")
  })

  it("keeps it when the secret is one the server holds and this screen never saw", () => {
    const merged = mergeParsedOptions({
      shape,
      fields,
      current: { auth_method: "with_secret", host: "old", user: "ann", secret: "" },
      parsed: { auth_method: "without_secret", host: "new", user: "ann" },
      secretsAreStored: true,
    })

    expect(merged.auth_method).toBe("with_secret")
  })

  it("takes the switch when there is no secret to lose", () => {
    const merged = mergeParsedOptions({
      shape,
      fields,
      current: { auth_method: "with_secret", host: "old", user: "ann", secret: "" },
      parsed: { auth_method: "without_secret", host: "new", user: "ann" },
      secretsAreStored: false,
    })

    expect(merged.auth_method).toBe("without_secret")
  })

  it("takes the switch when the text did say how to authenticate", () => {
    // A pasted address that names a way of connecting which needs a secret
    // said something about authentication, and that is an answer rather than
    // the absence of one — even though a secret is on screen to lose.
    const merged = mergeParsedOptions({
      shape,
      fields,
      current: { auth_method: "with_secret", host: "old", user: "ann", secret: "s3cret" },
      parsed: { auth_method: "with_other_secret", host: "new", token: "t0ken" },
      secretsAreStored: true,
    })

    expect(merged.auth_method).toBe("with_other_secret")
    expect(merged.token).toBe("t0ken")
  })

  it("has nothing to protect when the schema offers no choice", () => {
    const plain: SchemaShape = { kind: "plain", fields }
    const merged = mergeParsedOptions({
      shape: plain,
      fields,
      current: { host: "old", secret: "s3cret" },
      parsed: { host: "new" },
      secretsAreStored: false,
    })

    expect(merged.secret).toBe("s3cret")
    expect(merged.host).toBe("new")
  })
})
