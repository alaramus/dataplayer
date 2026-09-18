import type { AttachmentRules } from "@/client"

export type AttachmentKind = "image" | "text"

/**
 * Types a browser gives text that is not `text/*`. A file of an unknown type
 * (an empty `type`) is let through: the server reads its bytes and decides.
 */
const TEXTUAL = new Set([
  "application/json",
  "application/xml",
  "application/yaml",
  "application/x-yaml",
  "application/sql",
  "application/javascript",
  "application/x-sh",
  "application/toml",
])

/** Offered in the file picker beside the images, for the files people keep text in. */
const TEXT_ACCEPT = "text/*,.md,.csv,.tsv,.json,.log,.sql,.yaml,.yml,.xml,.toml,.ini,.py,.js,.ts,.sh"

export function kindOf(file: File, rules: AttachmentRules): AttachmentKind {
  return rules.image_types.includes(file.type) ? "image" : "text"
}

function readsAsText(file: File): boolean {
  return file.type === "" || file.type.startsWith("text/") || TEXTUAL.has(file.type)
}

/** What the file picker offers: images only to a model that reads them (D142). */
export function acceptFor(rules: AttachmentRules, readsImages: boolean): string {
  return readsImages ? `${rules.image_types.join(",")},${TEXT_ACCEPT}` : TEXT_ACCEPT
}

function size(bytes: number): string {
  return bytes >= 1024 * 1024 ? `${String(Math.floor(bytes / (1024 * 1024)))} MB` : `${String(Math.floor(bytes / 1024))} KB`
}

/** A file's size as the chip beside it says it. */
export function shownSize(bytes: number): string {
  if (bytes < 1024) return `${String(bytes)} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/**
 * Which picked files join the message, and a sentence for each that does not.
 *
 * The server reads every file again and has the last word (D142); this only
 * spares somebody sending twenty megabytes to be told what the numbers it was
 * given already say. The numbers are the server's, never a copy of them.
 */
export function admit(
  picked: readonly File[],
  held: readonly File[],
  rules: AttachmentRules,
  model: { name: string; readsImages: boolean }
): { taken: File[]; refused: string[] } {
  const taken: File[] = []
  const refused: string[] = []
  let total = held.reduce((sum, file) => sum + file.size, 0)
  for (const file of picked) {
    if (held.length + taken.length >= rules.max_files) {
      refused.push(`A message carries at most ${String(rules.max_files)} files`)
      break
    }
    const kind = kindOf(file, rules)
    if (kind === "image" && !model.readsImages) {
      refused.push(`${model.name} does not read images`)
      continue
    }
    if (kind === "image" && file.size > rules.max_image_bytes) {
      refused.push(`${file.name} is larger than ${size(rules.max_image_bytes)}`)
      continue
    }
    if (kind === "text" && !readsAsText(file)) {
      refused.push(`${file.name} is neither text nor a PNG, JPEG, WebP or GIF image`)
      continue
    }
    if (kind === "text" && file.size > rules.max_text_bytes) {
      refused.push(`${file.name} is larger than ${size(rules.max_text_bytes)} of text`)
      continue
    }
    if (total + file.size > rules.max_total_bytes) {
      refused.push(`The files of one message come to more than ${size(rules.max_total_bytes)}`)
      continue
    }
    total += file.size
    taken.push(file)
  }
  return { taken, refused }
}
