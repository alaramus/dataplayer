import { t } from "@/shared/i18n"

export function emptyRecipientsMessage(directoryCount: number, candidateCount: number): string {
  if (candidateCount > 0) return ""
  return directoryCount === 0
    ? t("shares.recipients.none_available")
    : t("shares.recipients.all_have_access")
}
