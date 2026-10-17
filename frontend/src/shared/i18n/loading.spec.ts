import { describe, expect, it, vi } from "vitest"

import { applyLanguage, currentLanguage, t } from "@/shared/i18n"

// The Russian chunk does not arrive, as when a deployment replaced it under an
// open tab.
vi.mock("@/shared/i18n/locales/ru", () => {
  throw new Error("Failed to fetch dynamically imported module")
})

describe("a language that cannot be loaded", () => {
  it("leaves the interface in the language it already speaks", async () => {
    await expect(applyLanguage("ru")).resolves.toBeUndefined()

    expect(currentLanguage()).toBe("en")
    expect(t("preferences.title")).toBe("Preferences")
    localStorage.clear()
  })
})
