import type { CloudAccountPublic } from "@/client"
import { readSchema } from "@/shared/SchemaForm/jsonSchema"
import type { FieldSpec, JsonSchema } from "@/shared/SchemaForm/jsonSchema"

/** How an account reads where one is chosen: its name and how it signs in. */
export function accountChoiceLabel(account: Pick<CloudAccountPublic, "name" | "method_title">): string {
  return `${account.name} · ${account.method_title}`
}

/**
 * A field that holds one of the owner's cloud accounts, offered as a choice
 * of those of the kinds it takes (D451). An id the connection holds and the
 * list no longer has stays as it is, so opening the form changes nothing.
 */
export function withAccountChoices(
  fields: FieldSpec[],
  accounts: readonly CloudAccountPublic[]
): FieldSpec[] {
  return fields.map((field) =>
    field.purpose === "cloud-account"
      ? {
          ...field,
          kind: "select",
          choices: accounts
            .filter((account) => field.accountKinds?.includes(account.kind) ?? false)
            .map((account) => ({ value: account.id, label: accountChoiceLabel(account) })),
        }
      : field
  )
}

/**
 * The fields an account of one kind shows for the method chosen, the choice
 * of method among them when the kind offers several.
 */
export function accountFields(schema: JsonSchema, method: unknown): FieldSpec[] {
  const shape = readSchema(schema)
  if (shape.kind === "plain") return shape.fields
  const chosen = typeof method === "string" ? method : String(shape.discriminator.defaultValue)
  return shape.byVariant[chosen] ?? shape.byVariant[String(shape.discriminator.defaultValue)] ?? []
}

/** The settings to send: only what the chosen method shows, so another
    method's leftovers are not refused as fields it does not have. */
export function settingsFor(fields: FieldSpec[], values: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    fields.filter((field) => field.name in values).map((field) => [field.name, values[field.name]])
  )
}
