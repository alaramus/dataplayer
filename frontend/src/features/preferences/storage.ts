import type { StorageUsage } from "@/client"
import { formatSize } from "@/features/catalog/nodes"
import { t } from "@/shared/i18n"

/** What the setting row says of a person's storage, and how full its bar is (D324). */
export function storageWording(usage: StorageUsage): { text: string; fraction: number | null } {
  const used = formatSize(usage.used_bytes)
  if (usage.limit_bytes === null || usage.limit_bytes === undefined) {
    return { text: t("preferences.storage_unlimited", { used }), fraction: null }
  }
  return {
    text: t("preferences.storage_used", { used, limit: formatSize(usage.limit_bytes) }),
    fraction: usage.used_bytes / usage.limit_bytes,
  }
}
