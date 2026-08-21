import { ref } from "vue"
import type { ZodType } from "zod"

import { defaultValues } from "./jsonSchema"
import type { FieldSpec } from "./jsonSchema"

export interface ServerError {
  loc: (string | number)[]
  msg: string
  type: string
}

/**
 * State of a form built from an adapter schema at runtime.
 *
 * A form library brings no benefit here: its main value is inferring types
 * from a static schema, and this schema is only known at runtime.
 */
export function useSchemaForm() {
  const values = ref<Record<string, unknown>>({})
  const errors = ref<Record<string, string>>({})

  function reset(fields: FieldSpec[], initial: Record<string, unknown> = {}) {
    values.value = { ...defaultValues(fields), ...initial }
    errors.value = {}
  }

  function validate(schema: ZodType): boolean {
    const result = schema.safeParse(values.value)
    if (result.success) {
      errors.value = {}
      return true
    }

    const collected: Record<string, string> = {}
    for (const issue of result.error.issues) {
      const name = String(issue.path[0] ?? "")
      if (name && !collected[name]) {
        collected[name] = issue.message
      }
    }
    errors.value = collected
    return false
  }

  function applyServerErrors(detail: ServerError[]) {
    const collected: Record<string, string> = {}
    for (const error of detail) {
      // The path looks like ["body", "options", "<field>"]; anything shorter
      // does not address a field.
      const name = error.loc.at(-1)
      if (typeof name === "string" && error.loc.length > 2) {
        collected[name] = error.msg
      }
    }
    errors.value = collected
  }

  return { values, errors, reset, validate, applyServerErrors }
}
