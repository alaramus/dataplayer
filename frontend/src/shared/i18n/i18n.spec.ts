import { baseCompile } from "@intlify/message-compiler"
import { afterEach, describe, expect, it } from "vitest"

import {
  applyLanguage,
  browserLanguage,
  currentLanguage,
  i18n,
  initialLanguage,
  LANGUAGE_KEY,
  LANGUAGES,
  t,
} from "@/shared/i18n"
import type { MessageKey } from "@/shared/i18n"
import { en } from "@/shared/i18n/locales/en"

/** Every key English has, the way `t` takes them. */
function keysOf(tree: object, prefix = ""): MessageKey[] {
  return Object.entries(tree).flatMap(([key, value]) =>
    typeof value === "string"
      ? [`${prefix}${key}` as MessageKey]
      : keysOf(value as object, `${prefix}${key}.`)
  )
}

afterEach(async () => {
  localStorage.clear()
  await applyLanguage("en")
  localStorage.clear()
})

describe("which language the interface opens in", () => {
  it("takes the first language the browser asks for that it speaks", () => {
    expect(browserLanguage(["de-DE", "ru-RU", "en"])).toBe("de")
    expect(browserLanguage(["RU"])).toBe("ru")
    expect(browserLanguage(["ja", "de"])).toBe("de")
    expect(browserLanguage(["ja", "fr"])).toBe("fr")
    expect(browserLanguage(["ja", "zh"])).toBe("zh")
    expect(browserLanguage(["ja", "hi"])).toBe("hi")
    expect(browserLanguage(["ja", "es"])).toBe("es")
    expect(browserLanguage(["ar-EG"])).toBe("ar")
    expect(browserLanguage(["ja", "ko"])).toBe("en")
    expect(browserLanguage([])).toBe("en")
  })

  it("prefers what this browser remembers of the account over the browser", () => {
    localStorage.setItem(LANGUAGE_KEY, "ru")
    expect(initialLanguage()).toBe("ru")

    // Written by a later version, or by hand: not a language, so not an answer.
    localStorage.setItem(LANGUAGE_KEY, "tlh")
    expect(initialLanguage()).toBe(browserLanguage())
  })

  it("remembers a chosen language and forgets it when the account chooses the browser's", async () => {
    await applyLanguage("ru")
    expect(localStorage.getItem(LANGUAGE_KEY)).toBe("ru")
    expect(currentLanguage()).toBe("ru")
    expect(document.documentElement.lang).toBe("ru")

    await applyLanguage(null)
    expect(localStorage.getItem(LANGUAGE_KEY)).toBeNull()
    expect(currentLanguage()).toBe(browserLanguage())
  })

  it("reads Arabic from the right and the others from the left", async () => {
    await applyLanguage("ar")
    expect(document.documentElement.lang).toBe("ar")
    expect(document.documentElement.dir).toBe("rtl")

    await applyLanguage("es")
    expect(document.documentElement.dir).toBe("ltr")
  })
})

describe("the dictionaries", () => {
  // The type checker proves every language has every key; this proves each
  // one is a message vue-i18n can read, since `{`, `}`, `@`, `|` and `$` are
  // its syntax and a stray one shows the key instead of the words.
  // vue-i18n says so only in a warning and answers with some words anyway, so
  // its own compiler is asked.
  it.each(LANGUAGES)("every message in %s is one vue-i18n can read", async (language) => {
    await applyLanguage(language)
    const messages = i18n.global.getLocaleMessage(language)

    for (const key of keysOf(en)) {
      const source = key.split(".").reduce<unknown>((node, part) => (node as Record<string, unknown>)[part], messages)
      const errors: string[] = []
      baseCompile(String(source), { onError: (error) => errors.push(error.message) })
      expect(errors, `${language} ${key}`).toEqual([])
      // The one mistake the compiler forgives: a `{` left open at the end is dropped.
      const count = (mark: string) => String(source).split(mark).length
      expect(count("{"), `${language} ${key}`).toBe(count("}"))
      // Every parameter filled, so a message that is one parameter is not blank.
      const params = Object.fromEntries(
        [...String(source).matchAll(/\{(\w+)\}/g)].map(([, name]) => [name, "X"])
      )
      expect(t(key, params).trim(), key).not.toBe("")
    }
  })

  it("counts in Russian by Russian rules", async () => {
    await applyLanguage("ru")
    i18n.global.mergeLocaleMessage("ru", { probe: "{n} строка | {n} строки | {n} строк | {n} строки" })
    const rows = (n: number) => i18n.global.t("probe", { n }, n)

    expect([1, 2, 5, 11, 21, 22, 25, 1.5].map(rows)).toEqual([
      "1 строка",
      "2 строки",
      "5 строк",
      "11 строк",
      "21 строка",
      "22 строки",
      "25 строк",
      "1.5 строки",
    ])
  })

  it("follows the language it is read in", async () => {
    expect(t("preferences.title")).toBe("Preferences")

    await applyLanguage("ru")
    expect(t("preferences.title")).toBe("Настройки")
  })
})
