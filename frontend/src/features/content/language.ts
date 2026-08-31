import { LanguageDescription } from "@codemirror/language"
import { languages } from "@codemirror/language-data"

/** Let CodeMirror's maintained metadata identify a language, not this app. */
export function languageFor(
  filename: string,
  hint?: string | null
): LanguageDescription | null {
  if (hint) {
    const hinted = LanguageDescription.matchLanguageName(languages, hint, true)
    if (hinted) return hinted
  }
  return LanguageDescription.matchFilename(languages, filename)
}
