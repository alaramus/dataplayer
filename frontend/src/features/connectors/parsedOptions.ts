import { defaultValues } from "@/shared/SchemaForm/jsonSchema"
import type { FieldSpec, SchemaShape } from "@/shared/SchemaForm/jsonSchema"

export interface ParsedMerge {
  /** What the schema turned out to be, or null while it is still loading. */
  shape: SchemaShape | null
  /** Every field the schema can produce, whichever variant is chosen. */
  fields: FieldSpec[]
  /** What the form holds now. */
  current: Record<string, unknown>
  /** What the driver made of the text in the box. */
  parsed: Record<string, unknown>
  /**
   * Whether the server holds secrets this screen was never sent, which is
   * what an untouched secret field means while editing a stored connection.
   */
  secretsAreStored: boolean
}

/** The secret fields of one variant, as the schema declares them. */
function secretsOf(shape: SchemaShape, tag: string): FieldSpec[] {
  if (shape.kind !== "variants") return []
  return (shape.byVariant[tag] ?? []).filter((field) => field.kind === "password")
}

/**
 * Whether believing the parsed choice would drop a secret the form is holding.
 *
 * A composed address never carries a secret, so taking one apart can only ever
 * answer with a way of connecting that needs none. Editing the host of a
 * connection that does need one would therefore switch the choice under the
 * user and hide what they had just typed.
 *
 * Stated about secrets and variants and not about any one source: both come
 * from the schema, and nothing here knows what a database is.
 */
function wouldDropHeldSecret(
  shape: SchemaShape,
  current: Record<string, unknown>,
  parsed: Record<string, unknown>,
  secretsAreStored: boolean
): boolean {
  if (shape.kind !== "variants") return false
  const chosen = current[shape.discriminator.name]
  const answered = parsed[shape.discriminator.name]
  if (typeof chosen !== "string" || typeof answered !== "string") return false
  if (chosen === answered) return false
  // The text did say how to authenticate, and an answer is an answer.
  if (secretsOf(shape, answered).length > 0) return false
  return secretsOf(shape, chosen).some((field) => {
    const held = current[field.name]
    return secretsAreStored || (typeof held === "string" && held !== "")
  })
}

/**
 * The form, after an address typed into the box was taken apart by the driver.
 *
 * Merged rather than reset: the driver answers about the parts of the address
 * the text held, and editing one part must not blank the rest. Three layers,
 * weakest first — what the schema defaults to, what is on screen, what the
 * driver said — so a field the form never held still arrives with a value.
 */
export function mergeParsedOptions({
  shape,
  fields,
  current,
  parsed,
  secretsAreStored,
}: ParsedMerge): Record<string, unknown> {
  const answer = { ...parsed }
  if (shape?.kind === "variants" && wouldDropHeldSecret(shape, current, parsed, secretsAreStored)) {
    // Dropped rather than overwritten: without a choice of its own in the
    // answer, the merge leaves the one on screen and the fields under it
    // exactly where they were.
    delete answer[shape.discriminator.name]
  }
  return { ...defaultValues(fields), ...current, ...answer }
}
