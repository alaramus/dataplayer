import type { InjectionKey } from "vue"

/**
 * The Help Center as the shell reaches it: the user menu lives in the kit,
 * which knows no feature, so the application hands it what opens the guide
 * and the key that does the same.
 */
export interface HelpCenter {
  open: () => void
  /** The key as a person reads it: "F1". */
  keys: string
}

export const helpCenterKey: InjectionKey<HelpCenter> = Symbol("help-center")
