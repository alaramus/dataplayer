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
 * Состояние формы, построенной из схемы адаптера в рантайме.
 *
 * Библиотека форм здесь не нужна: её основная ценность — вывод типов из
 * статической схемы, а наша схема известна только во время выполнения.
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
      // Путь имеет вид ["body", "options", "<поле>"]; всё короче поля не касается.
      const name = error.loc.at(-1)
      if (typeof name === "string" && error.loc.length > 2) {
        collected[name] = error.msg
      }
    }
    errors.value = collected
  }

  return { values, errors, reset, validate, applyServerErrors }
}
