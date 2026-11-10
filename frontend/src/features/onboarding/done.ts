import { computed } from "vue"

import { usePreferences, useUpdatePreferences } from "@/features/preferences/api"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import { useToast } from "@/shared/ui"

import type { TourDefinition } from "./tour"

/**
 * Which tours were taken or turned down, kept on the account so no other
 * browser of this person offers them again: the welcome's own as
 * `welcome_tour_done`, the short ones in `tours_done` (D356).
 */
export function useTourDone() {
  const preferences = usePreferences()
  const save = useUpdatePreferences()
  const toast = useToast()
  const welcomeDone = computed(() => preferences.data.value?.welcome_tour_done === true)
  const taken = computed(() => new Set<string>(preferences.data.value?.tours_done ?? []))

  function isDone(id: TourDefinition["id"]): boolean {
    return id === "basics" ? welcomeDone.value : taken.value.has(id)
  }

  async function markDone(id: TourDefinition["id"] = "basics") {
    if (isDone(id)) return
    try {
      await save.mutateAsync(id === "basics" ? { welcome_tour_done: true } : { tour_done: id })
    } catch (cause) {
      toast.error(messageOf(cause, t("onboarding.mark_failed")))
    }
  }

  return { done: welcomeDone, isDone, markDone }
}
