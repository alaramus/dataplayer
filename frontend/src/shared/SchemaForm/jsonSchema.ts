import { z } from "zod"

import { t } from "@/shared/i18n"

export interface JsonSchemaProperty {
  type?: string
  title?: string
  /** The sentence under the field: what to write, or what empty means. */
  description?: string
  /**
   * What a filled field looks like. JSON Schema's own keyword, a list because
   * the standard says so; the form shows the first and nothing else, inside
   * the empty control.
   */
  examples?: unknown[]
  /** The single value a discriminator property may take, as Pydantic emits it. */
  const?: string
  format?: string
  writeOnly?: boolean
  default?: unknown
  enum?: string[]
  /**
   * What each value is called, when the source has better words than the
   * value itself. `dbml` is a value; "DBML (dbdiagram.io)" is what somebody
   * recognises, and only the source knows the difference.
   */
  "x-ui-choices"?: { value: string; label: string }[]
  minLength?: number
  minimum?: number
  maximum?: number
  "x-ui-hidden"?: boolean
  /**
   * Whether the value is written on several lines — the members of a set, one
   * per line. Said by the model that declares the field, because the type is
   * `str` either way and a form inferring "long" from "string" would give
   * every host name six lines.
   */
  "x-ui-multiline"?: boolean
  /**
   * What the value means, beyond its type, when the form has to do more with
   * it than show a box. `grouping` says the field takes the id of one of the
   * source's own groupings — a schema, for a database — so the form offers
   * the ones this connection has instead of asking for an exact name.
   * `ssh-key` takes one of the owner's SSH keys (D146), and `ssh-host-key`
   * the server key a person confirmed (D145). `ssh-connection` takes one of
   * the owner's SSH connections, for a database reached through it (D282).
   */
  "x-ui-purpose"?:
    | "clipboard-mode"
    | "clipboard-nodes"
    | "file-conflict"
    | "filename-stem"
    | "grouping"
    | "node-name"
    | "ssh-key"
    | "ssh-host-key"
    | "ssh-connection"
  // Where the field goes, put here by `layout()` on the server. A statement
  // about the fields, so it is made where the fields are declared — the form
  // would otherwise have to infer that a port is narrow from its being a
  // number, which is a rule about addresses in a component that knows none.
  group?: string
  row?: string
  /**
   * How Pydantic writes a field that may be left out: the type it takes, and
   * null. Everything about the value — its bounds, its format — is inside the
   * branch rather than beside it, so a reader that ignored this would find a
   * field with no type at all.
   */
  anyOf?: JsonSchemaProperty[]
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
  "x-ui-workflow"?: "file-to-relation" | "model-as-code" | "table-designer" | "hypertable-settings"
}

export type FieldKind =
  | "text"
  | "multiline"
  | "password"
  | "number"
  | "boolean"
  | "datetime"
  | "select"
  | "hidden"

export interface FieldSpec {
  name: string
  label: string
  /**
   * What the source says about the value, shown under the field.
   *
   * Written where the field is declared and never here: "one per line, as
   * field=value" is a fact about a Redis hash, and a form has no way to know
   * it. It was travelling in the schema and being dropped on the floor until
   * a form needed to say how to write a value.
   */
  description?: string
  /**
   * What a filled field looks like, shown inside the empty one and gone the
   * moment anything is typed.
   *
   * A sentence says how to write a hash; this shows it, which is the
   * difference between reading an instruction and recognising a shape. Only
   * the model that declares the field knows one.
   */
  example?: string
  kind: FieldKind
  required: boolean
  defaultValue?: unknown
  choices?: SchemaChoice[]
  minLength?: number
  minimum?: number
  maximum?: number
  purpose?: JsonSchemaProperty["x-ui-purpose"]
  /** The tab this field belongs to. */
  group: string
  /** Fields sharing a row are laid out on one line. */
  row?: string
}

/**
 * One property, with an optional field's two branches folded back into it.
 *
 * `int | None` reaches the client as `anyOf: [{type: "integer", …}, {type:
 * "null"}]`, and the bounds go with the branch rather than staying beside it.
 * Folding the non-null branch back in makes it an ordinary field with
 * `required: false`, which is what the rest of this module knows how to draw.
 * Anything else with an `anyOf` fails loudly below.
 */
function flattened(property: JsonSchemaProperty): JsonSchemaProperty {
  const branches = property.anyOf
  if (branches === undefined || branches.length !== 2) return property
  const value = branches.find((branch) => branch.type !== "null")
  const nothing = branches.find((branch) => branch.type === "null")
  if (value === undefined || nothing === undefined) return property
  // The outer property wins: the title, the default and the layout are stated
  // where the field is, not inside one of its branches.
  return { ...value, ...property, anyOf: undefined }
}

function kindOf(property: JsonSchemaProperty, name: string): FieldKind {
  if (property["x-ui-hidden"] === true) return "hidden"
  if (property.enum) return "select"
  switch (property.type) {
    case "string":
      // Pydantic renders SecretStr as a string with format: password.
      if (property.format === "password") return "password"
      // An instant with its zone, which a calendar can write as well as a keyboard.
      if (property.format === "date-time") return "datetime"
      return property["x-ui-multiline"] === true ? "multiline" : "text"
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

/**
 * What each field the source gave names for offers, by field name.
 *
 * Read without building a form, because a workflow's schema may hold a
 * property no form can render — a list of column mappings — and asking for
 * its fields is meant to fail loudly. A screen of its own still needs the
 * words the source chose for a choice it publishes.
 */
export function choicesOf(schema: JsonSchema): Record<string, SchemaChoice[]> {
  return Object.fromEntries(
    Object.entries(schema.properties ?? {}).flatMap(([name, property]) => {
      const offered = property["x-ui-choices"]
      return offered === undefined ? [] : [[name, offered] as const]
    })
  )
}

/**
 * What each field starts as, read the same way and for the same reason.
 *
 * A screen of its own must open on what the source calls the default, not on
 * whichever value happens to be listed first — two statements that agree only
 * by convention are two statements to keep in step.
 */
export function defaultsOf(schema: JsonSchema): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(schema.properties ?? {}).flatMap(([name, property]) =>
      property.default === undefined ? [] : [[name, property.default] as const]
    )
  )
}

/**
 * The one example a field is drawn with, as text.
 *
 * The first of the list and only when it is already a string: an example of a
 * number is a number, and `String(…)` over an object would put `[object
 * Object]` in a placeholder.
 */
function exampleOf(property: JsonSchemaProperty): string | undefined {
  const first = property.examples?.[0]
  if (typeof first === "string") return first
  return typeof first === "number" ? String(first) : undefined
}

export function schemaToFields(schema: JsonSchema): FieldSpec[] {
  const required = new Set(schema.required ?? [])

  return Object.entries(schema.properties ?? {}).map(([name, raw]) => {
    const property = flattened(raw)
    return {
    name,
    label: property.title ?? name,
    description: property.description,
    example: exampleOf(property),
    kind: kindOf(property, name),
    required: required.has(name),
    defaultValue: property.default,
    choices:
      property["x-ui-choices"] ??
      property.enum?.map((value) => ({ value, label: value })),
    minLength: property.minLength,
    minimum: property.minimum,
    maximum: property.maximum,
    purpose: property["x-ui-purpose"],
    group: property.group ?? DEFAULT_GROUP,
    row: property.row,
    }
  })
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

/**
 * What the browser is told to fill a field of a connection with: nothing.
 *
 * These are the credentials of a database, and the browser's are those of a
 * person signing in to a website. Saying nothing let Chrome read the pair of
 * fields as a login form and fill a saved address and password into a form for
 * connecting to a server, which then looked ready to test and save with
 * credentials from somewhere else entirely (U03).
 *
 * `new-password` rather than `off` on the secret, because a browser is free to
 * disregard `off` where it believes it is helping somebody sign in, and takes
 * the one that says "this is not that password" more seriously. Neither is a
 * guarantee: what a browser does with a form is the browser's to decide, which
 * is why nothing here is stated as prevention.
 */
export function autofillOf(field: FieldSpec): "off" | "new-password" {
  return field.kind === "password" ? "new-password" : "off"
}

function zodForField(field: FieldSpec): z.ZodType {
  switch (field.kind) {
    case "hidden":
      // Set by the source or by the screen, never typed, and not always text:
      // the chunks picked in a report travel as a list (D209).
      return z.unknown()
    case "select":
      return z.enum(
        (field.choices ?? []).map((choice) => choice.value) as [string, ...string[]],
        { error: t("schema_form.choose", { label: field.label }) }
      )
    case "boolean":
      return z.boolean()
    case "number": {
      let schema = z.number({ error: t("schema_form.is_number", { label: field.label }) })
      if (field.minimum !== undefined) {
        schema = schema.min(
          field.minimum,
          t("schema_form.at_least", { label: field.label, n: field.minimum })
        )
      }
      if (field.maximum !== undefined) {
        schema = schema.max(
          field.maximum,
          t("schema_form.at_most", { label: field.label, n: field.maximum })
        )
      }
      return schema
    }
    default: {
      let schema = z.string()
      // A required string field must not validate when empty. Its message is
      // a sentence about the field: zod's own is written for a developer,
      // "Too small: expected string to have >=1 characters" (D187).
      const minLength = field.minLength ?? (field.required ? 1 : 0)
      if (minLength > 0) {
        schema = schema.min(
          minLength,
          minLength === 1
            ? t("schema_form.required", { label: field.label })
            : t("schema_form.min_length", { label: field.label, n: minLength }, minLength)
        )
      }
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
