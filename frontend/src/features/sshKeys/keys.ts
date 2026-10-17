import type { SshKeyPublic, SshKeyUnlockWritable } from "@/client"
import { t } from "@/shared/i18n"
import { formatTime } from "@/shared/i18n/format"
import type { FieldSpec } from "@/shared/SchemaForm/jsonSchema"

/** How long an asked-for passphrase is held. The set is the server's (D147). */
export type UnlockMinutes = NonNullable<SshKeyUnlockWritable["minutes"]>

const UNLOCK_LABELS: Record<UnlockMinutes, string> = {
  get 15() { return t("ssh_keys.unlock_spans.m15") },
  get 60() { return t("ssh_keys.unlock_spans.h1") },
  get 480() { return t("ssh_keys.unlock_spans.h8") },
}

export function unlockOptions(): { label: string; value: UnlockMinutes }[] {
  return ([15, 60, 480] as const).map((value) => ({ label: UNLOCK_LABELS[value], value }))
}

export type PassphraseMode = SshKeyPublic["passphrase_mode"]

const MODE_LABELS: Record<PassphraseMode, string> = {
  get none() { return t("ssh_keys.modes.none") },
  get stored() { return t("ssh_keys.modes.stored") },
  get ask() { return t("ssh_keys.modes.ask") },
}

export function passphraseModeLabel(mode: PassphraseMode): string {
  return MODE_LABELS[mode]
}

/**
 * Whether a key can be used right now, in the words beside it.
 *
 * Only a key that asks has a state worth saying: it is open until a time, or
 * shut. The time is the server's, shown in the reader's own clock.
 */
export function keyState(
  key: Pick<SshKeyPublic, "passphrase_mode" | "unlocked_until">
): { text: string; open: boolean } | null {
  if (key.passphrase_mode !== "ask") return null
  if (!key.unlocked_until) return { text: t("ssh_keys.state.locked"), open: false }
  const until = new Date(key.unlocked_until)
  const time = formatTime(until, { hour: "2-digit", minute: "2-digit" })
  return { text: t("ssh_keys.state.unlocked_until", { time }), open: true }
}

/** The tail of a fingerprint, which is what a person compares by eye. */
export function shortFingerprint(fingerprint: string): string {
  const body = fingerprint.replace(/^SHA256:/, "")
  return body.length > 12 ? `…${body.slice(-12)}` : body
}

/**
 * How much of a chosen file is read as a key. Not the server's limit on a key,
 * which is its own and says so when it refuses: this only keeps a file that
 * was picked by mistake — a video, a disk image — out of the page.
 */
export const MAX_KEY_FILE_BYTES = 64 * 1024

/**
 * The text of a key file, read here in the browser.
 *
 * It travels in the same request as a pasted key and is judged by the same
 * check on the server, so the file itself is never uploaded: an unencrypted
 * private key does not land on the server's disk even for a moment (D146).
 */
export async function readKeyFile(file: File): Promise<string> {
  if (file.size > MAX_KEY_FILE_BYTES) {
    throw new Error(t("ssh_keys.file_too_large"))
  }
  return await file.text()
}

/**
 * A sentence with commands and paths in it, cut where each one stands so it
 * can be drawn as code. The sentence is translated with every `{name}` left
 * in place, and the code itself is never translated.
 */
export function codeParts(
  sentence: string,
  codes: Record<string, string>
): { text: string; code: boolean }[] {
  return sentence.split(/\{(\w+)\}/).flatMap((part, index): { text: string; code: boolean }[] => {
    if (index % 2 === 1) return [{ text: codes[part] ?? part, code: true }]
    return part === "" ? [] : [{ text: part, code: false }]
  })
}

/** Every `{name}` of `codes` as itself, so `t` leaves the places for `codeParts`. */
export function codePlaces(codes: Record<string, string>): Record<string, string> {
  return Object.fromEntries(Object.keys(codes).map((name) => [name, `{${name}}`]))
}

/** How a key reads where one is chosen: its name, its kind and enough of its fingerprint. */
export function keyChoiceLabel(key: SshKeyPublic): string {
  return `${key.name} · ${key.algorithm} · ${shortFingerprint(key.fingerprint)}`
}

/**
 * A field that holds one of the owner's keys, offered as a choice of them.
 *
 * The schema says what the field is for (`x-ui-purpose: ssh-key`); only this
 * screen knows which keys there are. A key whose id the connection holds but
 * the list no longer has stays in the choice as it is, so opening the form
 * does not quietly change what it says.
 */
export function withKeyChoices(fields: FieldSpec[], keys: SshKeyPublic[]): FieldSpec[] {
  return fields.map((field) =>
    field.purpose === "ssh-key"
      ? {
          ...field,
          kind: "select",
          choices: keys.map((key) => ({ value: key.id, label: keyChoiceLabel(key) })),
        }
      : field
  )
}

/**
 * The key a connection signs in with, found by the server's own answer to
 * "which connections use this key" rather than by reading the connection's
 * options. Only the owner's list holds it, so only the owner is offered to
 * open it (D147).
 */
export function keyUsedBy(keys: readonly SshKeyPublic[], connectorId: string): SshKeyPublic | null {
  return keys.find((key) => key.used_by.some((use) => use.id === connectorId)) ?? null
}
