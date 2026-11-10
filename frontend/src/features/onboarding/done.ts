import { computed } from "vue"

import { usePreferences, useUpdatePreferences } from "@/features/preferences/api"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import { useToast } from "@/shared/ui"

/**
 * Whether the welcome was taken or turned down, kept on the account so no
 * other browser of this person opens it again.
 */
export function useTourDone() {
  const preferences = usePreferences()
  const save = useUpdatePreferences()
  const toast = useToast()
  const done = computed(() => preferences.data.value?.welcome_tour_done === true)

  async function markDone() {
    if (done.value) return
    try {
      await save.mutateAsync({ welcome_tour_done: true })
    } catch (cause) {
      toast.error(messageOf(cause, t("onboarding.mark_failed")))
    }
  }

  return { done, markDone }
}
