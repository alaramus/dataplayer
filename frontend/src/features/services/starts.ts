import type { ServiceRequest } from "@/client"

/**
 * The two shapes a request to start a service can take.
 *
 * Named here rather than imported: the server declares them as a discriminated
 * union behind an alias, and the generator inlines an alias into the field
 * that uses it. The type is still the generated one — this only gives it a
 * name to write.
 */
export type StartRequest = NonNullable<ServiceRequest["start"]>

/** What a person filled in, before it is turned into one of those shapes. */
export interface StartForm {
  mode: "automatic" | "chosen"
  name: string
  user: string
  database: string
  publish: boolean
  sampleData: boolean
  /** Which credentials this template lets a person name (D80). */
  choosable: readonly string[]
  /** Whether there is anything this server could put in it. */
  offersSampleData: boolean
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
    publish: form.publish,
    sample_data: form.offersSampleData && form.sampleData,
  }
}

function named(form: StartForm, slot: "user" | "database"): string | null {
  if (!form.choosable.includes(slot)) return null
  const written = form[slot].trim()
  return written === "" ? null : written
}

/** Whether the form can be sent at all: a chosen start needs a name. */
export function canStart(form: StartForm): boolean {
  return form.mode === "automatic" || form.name.trim() !== ""
}
