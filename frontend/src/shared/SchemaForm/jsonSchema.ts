import { z } from "zod"

export interface JsonSchemaProperty {
  type?: string
  title?: string
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

export interface JsonSchema {
  type?: string
  title?: string
  required?: string[]
  properties: Record<string, JsonSchemaProperty>
}

export type FieldKind = "text" | "password" | "number" | "boolean" | "select"

export interface FieldSpec {
  name: string
  label: string
  kind: FieldKind
  required: boolean
  defaultValue?: unknown
  choices?: string[]
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

  return Object.entries(schema.properties).map(([name, property]) => ({
    name,
    label: property.title ?? name,
    kind: kindOf(property, name),
    required: required.has(name),
    defaultValue: property.default,
    choices: property.enum,
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
      return z.enum(field.choices as [string, ...string[]])
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

export function jsonSchemaToZod(schema: JsonSchema) {
  const shape: Record<string, z.ZodType> = {}

  for (const field of schemaToFields(schema)) {
    const fieldSchema = zodForField(field)
    shape[field.name] = field.required ? fieldSchema : fieldSchema.optional()
  }

  return z.object(shape)
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
