import type { ServiceRequestWritable } from "@/client"

/**
 * The two shapes a request to start a service can take.
 *
 * Named here rather than imported: the server declares them as a discriminated
 * union behind an alias, and the generator inlines an alias into the field
 * that uses it. The type is still the generated one — this only gives it a
 * name to write.
 *
 * The writable one, because this is what is sent: the generator splits a
 * model that holds a write-only field into two, and a typed password is
 * exactly such a field — it goes and never comes back.
 */
export type StartRequest = NonNullable<ServiceRequestWritable["start"]>

/** How the password of a service is decided, in the server's own three shapes. */
export type PasswordRequest = Extract<
  StartRequest,
  { mode: "chosen" }
>["password"]

/** What a person filled in, before it is turned into one of those shapes. */
export interface StartForm {
  mode: "automatic" | "chosen"
  name: string
  user: string
  database: string
  /**
   * Which port on this machine it answers on. Zero means the runtime picks a
   * free one, which is the right answer for anybody without a reason to care.
   */
  port: number
  /**
   * Whether it should want a password at all. Only ever false for a template
   * that says running without one is a configuration rather than a mistake.
   */
  wantsPassword: boolean
  /** One typed here, or empty to have the server make one up. */
  password: string
  sampleData: boolean
  /** Which credentials this template lets a person name (D80). */
  choosable: readonly string[]
  /** Whether there is anything this server could put in it. */
  offersSampleData: boolean
  /** Whether this template runs without a password at all. */
  optionalPassword: boolean
}

/**
 * The request a filled-in form means.
 *
 * A plain function, so what "automatic" leaves out is a thing with a test
 * rather than a shape assembled inside a component. An automatic start
 * carries nothing at all: every answer is the server's, including the name.
 *
 * A value typed into a field the template did not open is dropped rather than
 * sent — the server refuses one, and a form that sends what will be refused
 * is a form that lies. The fields are only rendered when the template opens
 * them, so this is the second of two locks rather than the only one.
 */
export function buildStart(form: StartForm): StartRequest {
  if (form.mode === "automatic") return { mode: "automatic" }
  return {
    mode: "chosen",
    name: form.name.trim(),
    user: named(form, "user"),
    database: named(form, "database"),
    port: portOf(form),
    password: passwordOf(form),
    sample_data: form.offersSampleData && form.sampleData,
  }
}

function named(form: StartForm, slot: "user" | "database"): string | null {
  if (!form.choosable.includes(slot)) return null
  const written = form[slot].trim()
  return written === "" ? null : written
}

/**
 * Zero for anything that is not a port somebody meant.
 *
 * A number field reports what was typed, and half-typed is a real state: the
 * server takes zero to mean "pick one", so that is what an unfinished number
 * becomes rather than a request it would refuse.
 */
function portOf(form: StartForm): number {
  if (!Number.isInteger(form.port) || form.port < 1 || form.port > 65535) return 0
  return form.port
}

/**
 * Which of the three ways the password is being decided.
 *
 * Empty means generated rather than empty: a person who left the field alone
 * has asked for the same thing the automatic start gives them, and sending an
 * empty string would be asking for a service with no password at all — which
 * is a different request, and one with its own answer.
 */
function passwordOf(form: StartForm): PasswordRequest {
  if (form.optionalPassword && !form.wantsPassword) return { kind: "none" }
  if (!form.choosable.includes("password") || form.password === "") {
    return { kind: "generated" }
  }
  return { kind: "chosen", value: form.password }
}

/**
 * What a password has to be, said the same way the server says it.
 *
 * Printable characters with no space among them, because the string becomes an
 * environment variable in a container specification, an argument on a command
 * line and part of a connection string. The server refuses one that is not;
 * this is here so the refusal is read before the button is pressed rather
 * than after.
 */
const USABLE_PASSWORD = /^[!-~]{8,128}$/

/** What is wrong with the password, when something is. */
export function passwordProblem(form: StartForm): string | null {
  if (form.mode === "automatic") return null
  if (form.optionalPassword && !form.wantsPassword) return null
  if (form.password === "") return null
  if (USABLE_PASSWORD.test(form.password)) return null
  return "8 to 128 characters, with no spaces and nothing exotic in it"
}

/** Whether the form can be sent at all: a chosen start needs a usable name. */
export function canStart(form: StartForm): boolean {
  if (form.mode === "automatic") return true
  return form.name.trim() !== "" && passwordProblem(form) === null
}
