import { t } from "@/shared/i18n"

/**
 * The most a field read from a file takes when its schema states no length.
 *
 * Far above any certificate chain or JSON key; it only keeps a file picked by
 * mistake — a video, a disk image — from being read into the page.
 */
export const MAX_FIELD_FILE_BYTES = 1024 * 1024

/**
 * The text of a file chosen or dropped on a field, or a refusal in words.
 *
 * Read in the browser: the field then holds exactly what a paste would have
 * put there, and the server checks it as it checks a paste. Refused here are
 * only what could never be the text of the field — a binary file (a DER
 * certificate, a PKCS#12 bundle) or one longer than the field takes.
 */
export async function readFieldFile(
  file: File,
  label: string,
  maxLength?: number
): Promise<string> {
  if (file.size > MAX_FIELD_FILE_BYTES) {
    throw new Error(t("schema_form.file_too_large", { label }))
  }
  // Blob.text() decodes UTF-8 and drops a byte-order mark, which a key saved
  // by a Windows editor may begin with and JSON.parse would refuse.
  const text = await file.text()
  if (text.includes("\u0000") || text.includes("�")) {
    throw new Error(t("schema_form.file_not_text", { label }))
  }
  if (maxLength !== undefined && text.length > maxLength) {
    throw new Error(t("schema_form.file_too_long", { label, n: maxLength }))
  }
  return text
}

/** The file a drag carries, when it carries exactly one. */
export function droppedFile(transfer: DataTransfer | null): File | null {
  const files = transfer?.files
  return files !== undefined && files.length === 1 ? (files[0] ?? null) : null
}
