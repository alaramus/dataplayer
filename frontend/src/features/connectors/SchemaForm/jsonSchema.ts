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
}

function kindOf(property: JsonSchemaProperty, name: string): FieldKind {
  if (property.enum) return "select"
  switch (property.type) {
    case "string":
      // Pydantic отдаёт SecretStr как строку с format: password.
      return property.format === "password" ? "password" : "text"
    case "integer":
    case "number":
      return "number"
    case "boolean":
      return "boolean"
    default:
      // Падаем громко: молча не отрисованное поле выглядит как потерянная
      // настройка подключения.
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
  }))
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
      // Обязательное строковое поле не должно проходить проверку пустым.
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
