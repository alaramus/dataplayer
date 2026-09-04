import { inject } from "vue"
import type { InjectionKey } from "vue"

import type { Operations } from "./operations"

export { createOperations, isActive } from "./operations"
export type { Operation, OperationHandle, Operations } from "./operations"

export const operationsKey: InjectionKey<Operations> = Symbol("operations")

export function useOperations(): Operations {
  const operations = inject(operationsKey)
  if (operations === undefined) throw new Error("The application has no operation registry")
  return operations
}
