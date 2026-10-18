import { Lang } from "quasar"
import type { QuasarLanguage } from "quasar"
import { createI18n } from "vue-i18n"

import type { PreferencesPublic } from "@/client"

import { en } from "./locales/en"
import type { Messages } from "./locales/en"
import { isProblem, wordProblem } from "./problems"
import type { ProblemCode } from "./problems"

/**
 * The language of the interface (D224).
 *
 * English is built in and is what any missing key falls back to; every other
 * language is a chunk of its own, loaded when somebody chooses it.
 */
export type Language = NonNullable<PreferencesPublic["language"]>

/** Each language by its own name, which is how somebody finds theirs. */
const NAMES: Record<Language, string> = {
  en: "English",
  ru: "Русский",
  de: "Deutsch",
}

export const LANGUAGES: readonly Language[] = Object.keys(NAMES) as Language[]

export function languageName(language: Language): string {
  return NAMES[language]
}

type Bundle = {
  messages: Messages
  problems: Record<ProblemCode, string> | null
  quasar: QuasarLanguage
}

/** How to fetch a language: its dictionaries and Quasar's own pack beside them. */
const LOADERS: Record<Language, () => Promise<Bundle>> = {
  en: async () => ({
    messages: en,
    // The server's sentence is the English (D225).
    problems: null,
    quasar: (await import("quasar/lang/en-US.js")).default,
  }),
  ru: async () => {
    const [own, quasar] = await Promise.all([
      import("./locales/ru"),
      import("quasar/lang/ru.js"),
    ])
    return { messages: own.messages, problems: own.problems, quasar: quasar.default }
  },
  de: async () => {
    const [own, quasar] = await Promise.all([
      import("./locales/de"),
      import("quasar/lang/de.js"),
    ])
    return { messages: own.messages, problems: own.problems, quasar: quasar.default }
  },
}

/**
 * The plural forms a message lists between its `|`, in order, for languages
 * whose forms are not English's. vue-i18n knows only English's; the language's
 * own rules come from the browser.
 */
const PLURAL_FORMS: Partial<Record<Language, readonly Intl.LDMLPluralRule[]>> = {
  ru: ["one", "few", "many", "other"],
}

function pluralRule(language: string, forms: readonly Intl.LDMLPluralRule[]) {
  const rules = new Intl.PluralRules(language)
  return (count: number, choices: number): number => {
    const index = forms.indexOf(rules.select(count))
    return Math.min(index < 0 ? forms.length - 1 : index, choices - 1)
  }
}

export const i18n = createI18n<[Messages], Language, false>({
  legacy: false,
  locale: "en",
  fallbackLocale: "en",
  messages: { en } as Record<Language, Messages>,
  // Words reach the page as text, never as HTML, so "<default>" is a word.
  warnHtmlMessage: false,
  pluralRules: Object.fromEntries(
    Object.entries(PLURAL_FORMS).map(([language, forms]) => [language, pluralRule(language, forms)])
  ),
})

/** Every key the English dictionary has, as `group.key`. */
type Leaves<T, Prefix extends string = ""> = {
  [K in keyof T & string]: T[K] extends string ? `${Prefix}${K}` : Leaves<T[K], `${Prefix}${K}.`>
}[keyof T & string]

export type MessageKey = Leaves<Messages>

/**
 * The interface's words, by key, in the current language. The one way to
 * them: vue-i18n's own `t` takes any string, so a mistyped key would compile
 * and show the key itself; this one takes only keys English has.
 *
 * Reactive wherever it is read — a template, a computed, a getter — because
 * it reads the current language. Never call it while a module loads: a
 * string taken at import is in whatever language was current then, and stays
 * in it. `count` chooses between a message's `|`-separated plural forms.
 */
export function t(key: MessageKey, params: Record<string, string | number> = {}, count?: number): string {
  return count === undefined ? i18n.global.t(key, params) : i18n.global.t(key, params, count)
}

const problemDictionaries: Partial<Record<Language, Record<ProblemCode, string> | null>> = {
  en: null,
}

export function currentLanguage(): Language {
  return i18n.global.locale.value
}

/** A refusal the server coded, in the current language; null for anything else. */
export function problemMessage(detail: unknown): string | null {
  if (!isProblem(detail)) return null
  return wordProblem(detail, problemDictionaries[currentLanguage()] ?? null)
}

export const LANGUAGE_KEY = "dataplayer-language"

function isLanguage(value: unknown): value is Language {
  return typeof value === "string" && value in NAMES
}

/** The first language the browser asks for that the interface speaks. */
export function browserLanguage(languages: readonly string[] = navigator.languages): Language {
  for (const tag of languages) {
    const base = tag.toLowerCase().split("-")[0]
    if (isLanguage(base)) return base
  }
  return "en"
}

/**
 * What to show before the account has said: the account's last choice as this
 * browser remembers it, so a Russian reader is not shown the sign-in page in
 * English, or the browser's own language.
 */
export function initialLanguage(): Language {
  try {
    const remembered = localStorage.getItem(LANGUAGE_KEY)
    if (isLanguage(remembered)) return remembered
  } catch {
    // Storage refused: the browser's language is still an answer.
  }
  return browserLanguage()
}

/**
 * Show the interface in a language, loading it first if needed.
 *
 * `chosen` null is the account choosing no language: the browser's is shown
 * and nothing is remembered, so the next sign-in page asks the browser again.
 */
export async function applyLanguage(chosen: Language | null): Promise<void> {
  const language = chosen ?? browserLanguage()
  try {
    if (chosen === null) localStorage.removeItem(LANGUAGE_KEY)
    else localStorage.setItem(LANGUAGE_KEY, chosen)
  } catch {
    // Remembering is a convenience for the next sign-in page, nothing more.
  }
  let bundle: Bundle
  try {
    bundle = await LOADERS[language]()
  } catch {
    // A chunk that did not arrive — a deployment replaced under an open tab,
    // a network blink — leaves the interface in what it already speaks
    // rather than without one.
    return
  }
  i18n.global.setLocaleMessage(language, bundle.messages)
  problemDictionaries[language] = bundle.problems
  Lang.set(bundle.quasar)
  const changed = i18n.global.locale.value !== language
  i18n.global.locale.value = language
  document.documentElement.lang = language
  if (changed) for (const listener of listeners) listener(language)
}

const listeners = new Set<(language: Language) => void>()

/**
 * Be told when the interface changes language. What the server worded
 * (D226) — an action's title, a form's labels — was cached in the old one and
 * is asked for again.
 */
export function onLanguageChange(listener: (language: Language) => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}
