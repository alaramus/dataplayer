import { computed } from "vue"

import { usePreferences, useUpdatePreferences } from "@/features/preferences/api"
import { messageOf } from "@/shared/api/errors"
import { applyLanguage, LANGUAGES, languageName, t } from "@/shared/i18n"
import type { Language } from "@/shared/i18n"
import { useToast } from "@/shared/ui"

// A choice holds no null, so the browser's language travels as a word of its
// own between a screen and the request.
const BROWSER = "browser"

/**
 * The account's language as a choice, wherever it is offered — Preferences,
 * and the welcome on a first visit (D224). One place, so both offer the same
 * options and save them the same way.
 */
export function useLanguageChoice() {
  const toast = useToast()
  const preferences = usePreferences()
  const save = useUpdatePreferences()

  const options = computed(() => [
    { value: BROWSER, label: t("language.browser"), description: t("language.browser_hint") },
    ...LANGUAGES.map((language) => ({ value: language, label: languageName(language) })),
  ])

  /** Undefined while the account has not been read; the browser's otherwise. */
  const chosen = computed(() => {
    const data = preferences.data.value
    return data === undefined ? undefined : (data.language ?? BROWSER)
  })

  async function choose(value: unknown) {
    if (value === chosen.value) return
    const language = value === BROWSER ? null : (value as Language)
    try {
      await save.mutateAsync({ language })
      // Before the toast, so it is already said in the language just chosen.
      await applyLanguage(language)
      toast.success(t("preferences.saved"))
    } catch (cause) {
      toast.error(messageOf(cause, t("preferences.not_saved")))
    }
  }

  return { options, chosen, choose, saving: save.isPending }
}
