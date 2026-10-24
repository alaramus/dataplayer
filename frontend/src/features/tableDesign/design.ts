import type { ComputedRef } from "vue"

import type { DesignTypeOption, FunctionOption, TableDesignOptions } from "@/client"
import type { SelectOption } from "@/shared/ui"

import type { Draft } from "./draft"

/**
 * The draft and what the server said may go in it, shared by every panel.
 *
 * Held in a registry and reached by name rather than passed down as an object.
 * Two things rule out the obvious alternatives: a draft handed over as a prop
 * cannot be edited without mutating one, which would turn every field into a
 * binding and an event for no gain; and provide/inject does not reach these
 * panels at all, because a floating window mounts its content under the window
 * host rather than under the component that opened it — the injection is
 * simply not on that parent chain.
 *
 * One entry per open designer, so two drafts side by side stay two drafts.
 */
export interface DesignContext {
  draft: Draft
  options: ComputedRef<TableDesignOptions | null>
  /** Every column of the draft as a choice, in the order they are declared. */
  columnChoices: ComputedRef<SelectOption[]>
  typeChoices: ComputedRef<SelectOption[]>
  types: ComputedRef<DesignTypeOption[]>
  functions: ComputedRef<FunctionOption[]>
  /** Whether the source calls its schemas databases (D229). */
  databases: ComputedRef<boolean>
}

const designs = new Map<string, DesignContext>()

let counter = 0

export function newDesignId(): string {
  counter += 1
  return `design-${String(counter)}`
}

export function registerDesign(id: string, context: DesignContext): void {
  designs.set(id, context)
}

export function forgetDesign(id: string): void {
  designs.delete(id)
}

export function useDesign(id: string): DesignContext {
  const context = designs.get(id)
  if (context === undefined) {
    throw new Error("A table design panel is only drawn inside the designer")
  }
  return context
}

/** The functions offered where this expression sits, in the source's words. */
export function functionChoices(
  functions: FunctionOption[],
  context: "default" | "generated" | "check" | "index" | "predicate",
  arity: number
): SelectOption[] {
  return functions
    .filter(
      (option) =>
        (option.contexts ?? []).includes(context) && (option.arity ?? 0) === arity
    )
    .map((option) => ({ label: option.signature, value: option.code }))
}
