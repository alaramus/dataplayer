import type { ComputedRef, InjectionKey } from "vue"

/** Which way a pair's values go: from the left column into the right, or back. */
export type PairsArrow = "forward" | "back"

export const pairsArrowKey: InjectionKey<ComputedRef<PairsArrow>> = Symbol("pairs-arrow")
