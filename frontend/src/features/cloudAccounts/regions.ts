import type { CloudRegion } from "@/client"
import type { FieldSpec } from "@/shared/SchemaForm/jsonSchema"

/**
 * A field naming an AWS region, offered as a choice of Amazon's regions
 * (D461): an account's own when the form names one, every published one
 * otherwise. The empty choice comes first, named in the field's own words
 * about what empty means.
 *
 * Left a typed field while there is no list — Amazon did not answer — and
 * while the field it names in `typedWhen` is filled: an S3 endpoint is
 * another provider's store, whose regions Amazon does not know. A region the
 * form holds and the list does not stays in the choice, so opening the form
 * does not change what it says.
 */
export function withRegionChoices(
  fields: FieldSpec[],
  regions: readonly CloudRegion[],
  values: Record<string, unknown>,
  empty: string
): FieldSpec[] {
  if (regions.length === 0) return fields
  return fields.map((field) => {
    if (field.purpose !== "aws-region") return field
    const other = field.typedWhen === undefined ? undefined : values[field.typedWhen]
    if (typeof other === "string" && other.trim() !== "") return field
    const held = values[field.name]
    const unseen =
      typeof held === "string" && held !== "" && !regions.some((region) => region.name === held)
        ? [{ value: held, label: held }]
        : []
    return {
      ...field,
      kind: "select",
      choices: [
        { value: "", label: empty },
        ...regions.map((region) => ({
          value: region.name,
          label: region.title === "" ? region.name : `${region.name} · ${region.title}`,
        })),
        ...unseen,
      ],
    }
  })
}

/** The account a form's region list is asked of: the one its AWS account field holds. */
export function regionAccount(fields: FieldSpec[], values: Record<string, unknown>): string | undefined {
  const field = fields.find(
    (one) => one.purpose === "cloud-account" && one.accountKinds?.length === 1 && one.accountKinds[0] === "aws"
  )
  const held = field === undefined ? undefined : values[field.name]
  return typeof held === "string" && held !== "" ? held : undefined
}
