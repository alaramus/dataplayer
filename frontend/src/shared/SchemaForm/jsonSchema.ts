import { z } from "zod"

export interface JsonSchemaProperty {
  type?: string
  title?: string
  /** The single value a discriminator property may take, as Pydantic emits it. */
  const?: string
  format?: string
  writeOnly?: boolean
  default?: unknown
  enum?: string[]
  minLength?: number
  minimum?: number
  maximum?: number
  // Where the field goes, put here by `layout()` on the server. A statement
  // about the fields, so it is made where the fields are declared — the form
  // would otherwise have to infer that a port is narrow from its being a
  // number, which is a rule about addresses in a component that knows none.
  group?: string
  row?: string
}

/** One member of a union, always a reference into `$defs`. */
export interface JsonSchemaRef {
  $ref: string
}

export interface JsonSchema {
  type?: string
  title?: string
  required?: string[]
  // Absent from the top level of a union schema: everything is in $defs there.
  properties?: Record<string, JsonSchemaProperty>
  $defs?: Record<string, JsonSchema>
  oneOf?: JsonSchemaRef[]
  discriminator?: {
    propertyName: string
    /** The code of a variant to the definition that describes it. */
    mapping: Record<string, string>
  }
}

export type FieldKind = "text" | "password" | "number" | "boolean" | "select"

export interface FieldSpec {
  name: string
  label: string
  kind: FieldKind
  required: boolean
  defaultValue?: unknown
  choices?: SchemaChoice[]
  minLength?: number
  minimum?: number
  maximum?: number
  /** The tab this field belongs to. */
  group: string
  /** Fields sharing a row are laid out on one line. */
  row?: string
}

function kindOf(property: JsonSchemaProperty, name: string): FieldKind {
  if (property.enum) return "select"
  switch (property.type) {
    case "string":
      // Pydantic renders SecretStr as a string with format: password.
      return property.format === "password" ? "password" : "text"
    case "integer":
    case "number":
      return "number"
    case "boolean":
      return "boolean"
    default:
      // Fail loudly: a field silently left unrendered looks like a lost
      // connection setting.
      throw new Error(`Unsupported property type "${property.type}" for field "${name}"`)
  }
}

export function schemaToFields(schema: JsonSchema): FieldSpec[] {
  const required = new Set(schema.required ?? [])

  return Object.entries(schema.properties ?? {}).map(([name, property]) => ({
    name,
    label: property.title ?? name,
    kind: kindOf(property, name),
    required: required.has(name),
    defaultValue: property.default,
    choices: property.enum?.map((value) => ({ value, label: value })),
    minLength: property.minLength,
    minimum: property.minimum,
    maximum: property.maximum,
    group: property.group ?? DEFAULT_GROUP,
    row: property.row,
  }))
}

/**
 * The tab a field lands on when its schema says nothing.
 *
 * Mirrors `DEFAULT_GROUP` in the backend's `layout.py`. Stated on both sides
 * because a schema written before that helper existed — or by a driver that
 * never calls it — must still render, and a field with no tab is not a field
 * to drop on the floor.
 */
export const DEFAULT_GROUP = "general"

export interface FieldGroup {
  id: string
  fields: FieldSpec[]
}

/**
 * The fields split into tabs, in the order the schema listed them.
 *
 * A window with one group draws no tab strip: one tab is not a choice.
 */
export function fieldGroups(fields: FieldSpec[]): FieldGroup[] {
  const groups: FieldGroup[] = []

  for (const field of fields) {
    const last = groups.find((group) => group.id === field.group)
    if (last) last.fields.push(field)
    else groups.push({ id: field.group, fields: [field] })
  }
  return groups
}

/**
 * The fields split into lines, adjacent members of one row together.
 *
 * Adjacency matters: matching by name alone would let a field further down the
 * form jump up to join a row above it, silently reordering what the schema
 * laid out. A run ends as soon as a field of another row appears.
 */
export function fieldRows(fields: FieldSpec[]): FieldSpec[][] {
  const rows: FieldSpec[][] = []
  let openRow: string | undefined

  for (const field of fields) {
    const last = rows[rows.length - 1]
    if (field.row !== undefined && field.row === openRow && last !== undefined) {
      last.push(field)
    } else {
      rows.push([field])
      openRow = field.row
    }
  }
  return rows
}

function zodForField(field: FieldSpec): z.ZodType {
  switch (field.kind) {
    case "select":
      return z.enum(
        (field.choices ?? []).map((choice) => choice.value) as [string, ...string[]]
      )
    case "boolean":
      return z.boolean()
    case "number": {
      let schema = z.number()
      if (field.minimum !== undefined) schema = schema.min(field.minimum)
      if (field.maximum !== undefined) schema = schema.max(field.maximum)
      return schema
    }
    default: {
      let schema = z.string()
      // A required string field must not validate when empty.
      const minLength = field.minLength ?? (field.required ? 1 : 0)
      if (minLength > 0) schema = schema.min(minLength)
      return schema
    }
  }
}

/**
 * What a set of fields accepts.
 *
 * Takes fields rather than a schema because a union is never validated whole:
 * the fields in hand are the common ones plus those of the variant the user
 * chose, and the whole union at once would demand a password that the chosen
 * way of connecting does not have.
 */
export function fieldsToZod(fields: FieldSpec[]) {
  const shape: Record<string, z.ZodType> = {}

  for (const field of fields) {
    const fieldSchema = zodForField(field)
    shape[field.name] = field.required ? fieldSchema : fieldSchema.optional()
  }

  return z.object(shape)
}

export function jsonSchemaToZod(schema: JsonSchema) {
  return fieldsToZod(schemaToFields(schema))
}

export function defaultValues(fields: FieldSpec[]): Record<string, unknown> {
  const values: Record<string, unknown> = {}

  for (const field of fields) {
    if (field.defaultValue !== undefined) {
      values[field.name] = field.defaultValue
    } else if (field.kind === "boolean") {
      values[field.name] = false
    } else if (field.kind === "number") {
      values[field.name] = null
    } else {
      values[field.name] = ""
    }
  }

  return values
}

/**
 * The one thing a variant of a schema is picked by.
 *
 * A pair rather than a bare string because the code stored in the options and
 * the wording a user reads are two different things: `no_auth` is what travels
 * to the server, "No auth" is what the model called itself.
 */
export interface SchemaChoice {
  value: string
  label: string
}

/**
 * What a schema turns out to be.
 *
 * A source type whose fields depend on the way it is connected to describes
 * them as a discriminated union, and Pydantic emits that as `$defs` plus
 * `oneOf` plus a `discriminator` — with nothing at the top level to read. A
 * union is marked out here rather than sniffed for at every call site.
 */
export type SchemaShape =
  | { kind: "plain"; fields: FieldSpec[] }
  | {
      kind: "variants"
      /** The choice itself: a select whose items are the variants. */
      discriminator: FieldSpec
      /**
       * Fields every variant has alike — what a switch of method must not
       * disturb. Not a rendering order: that comes from `byVariant`.
       */
      common: FieldSpec[]
      /**
       * Everything a variant shows, in the order its model declared it, the
       * choice among them.
       *
       * The order is the server's statement and not this function's: a model
       * puts the choice under the address by declaring it there, and a form
       * that gathered all the shared fields first would override that with a
       * rule of its own.
       */
      byVariant: Record<string, FieldSpec[]>
    }

function resolveRef(schema: JsonSchema, ref: string): JsonSchema {
  // Only local refs into $defs are ever emitted, and a schema that pointed
  // anywhere else would be a schema this form cannot render.
  const name = ref.replace("#/$defs/", "")
  const found = schema.$defs?.[name]
  if (!found) throw new Error(`Cannot resolve schema reference "${ref}"`)
  return found
}

/** True when two variants are talking about the same field. */
function sameField(one: FieldSpec, other: FieldSpec): boolean {
  return (
    one.name === other.name && one.kind === other.kind && one.label === other.label
  )
}

export function readSchema(schema: JsonSchema): SchemaShape {
  const discriminator = schema.discriminator
  if (!discriminator || !schema.oneOf) {
    return { kind: "plain", fields: schemaToFields(schema) }
  }

  // `oneOf` is in the order the variants were declared; the keys of `mapping`
  // are not, so the pick list is built from the first and named by the second.
  const tagOf = new Map(
    Object.entries(discriminator.mapping).map(([tag, ref]) => [ref, tag])
  )
  const variants = schema.oneOf.map((member) => {
    const tag = tagOf.get(member.$ref)
    if (tag === undefined) throw new Error(`No variant is mapped to "${member.$ref}"`)
    const definition = resolveRef(schema, member.$ref)
    return {
      tag,
      label: definition.title ?? member.$ref.replace("#/$defs/", ""),
      fields: schemaToFields(definition),
      property: definition.properties?.[discriminator.propertyName],
    }
  })

  const [firstVariant, ...rest] = variants
  if (!firstVariant) throw new Error("A union schema with no variants")

  const choice: FieldSpec = {
    name: discriminator.propertyName,
    label: firstVariant.property?.title ?? discriminator.propertyName,
    kind: "select",
    required: true,
    // The first variant, so a form that has been touched by nobody still
    // names a way of connecting: the server rejects options that name none.
    defaultValue: firstVariant.tag,
    choices: variants.map(({ tag, label }) => ({ value: tag, label })),
    group: firstVariant.property?.group ?? DEFAULT_GROUP,
    row: firstVariant.property?.row,
  }

  const isChoice = (field: FieldSpec) => field.name === choice.name
  const own = (variant: { fields: FieldSpec[] }) => variant.fields.filter((f) => !isChoice(f))

  const common = own(firstVariant).filter((field) =>
    rest.every((variant) => variant.fields.some((other) => sameField(field, other)))
  )

  const byVariant: Record<string, FieldSpec[]> = {}
  for (const variant of variants) {
    // In place rather than filtered out: Pydantic emits the discriminator as
    // a `const`, which would render as a text box holding the name of the
    // variant, so it is the select that stands where the model put it.
    byVariant[variant.tag] = variant.fields.map((field) =>
      isChoice(field) ? choice : field
    )
  }

  return { kind: "variants", discriminator: choice, common, byVariant }
}
