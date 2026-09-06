import { computed } from "vue"
import type { ComputedRef } from "vue"

import { useAdapterTypes } from "@/features/connectors/api"
import { useBackupOffer } from "@/features/services/api"

/**
 * Whether one connection could be copied out, which is two questions.
 *
 * One is about the source: only a type whose driver can name a program that
 * dumps it declares the `backup` capability, and neither a file source nor a
 * Redis server does — a source that cannot be copied out is offered nothing
 * rather than a line that never works. The other is about the machine: a
 * container runtime to run the dump in and somewhere to write what it
 * produces (D87). The refusal is whichever of the two said no.
 */
export interface BackupSupport {
  /** Whether the command is worth drawing for this kind of source at all. */
  offered: boolean
  enabled: boolean
  /** Why it cannot be used, or nothing when it can. */
  reason?: string
}

export function useBackupSupport(
  adapterType: () => string | null
): ComputedRef<BackupSupport> {
  const offer = useBackupOffer()
  const types = useAdapterTypes()
  return computed(() => {
    const name = adapterType()
    const declared =
      name === null
        ? false
        : (types.data.value ?? []).some(
            (type) =>
              type.name === name &&
              type.capabilities.some((capability) => capability.code === "backup")
          )
    if (!declared) return { offered: false, enabled: false }
    if (offer.isLoading.value) {
      return { offered: true, enabled: false, reason: "Asking this server what it can do" }
    }
    if (offer.data.value?.available !== true) {
      return {
        offered: true,
        enabled: false,
        reason: offer.data.value?.reason ?? "This server cannot copy a database out",
      }
    }
    return { offered: true, enabled: true }
  })
}
