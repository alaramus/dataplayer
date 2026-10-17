import { t } from "@/shared/i18n"
import type { PageSection } from "@/shared/ui"
import { appIcons } from "@/shared/ui/icons"

/** What Administration offers, in order; the page maps each id onto its body.
    Words are getters, read in the language current when they are shown. */
export const ADMIN_SECTIONS = [
  {
    id: "users",
    get title() { return t("admin.sections.users") },
    get summary() { return t("admin.sections.users_summary") },
    icon: appIcons.group,
  },
] as const satisfies readonly [PageSection, ...PageSection[]]

export type AdminSectionId = (typeof ADMIN_SECTIONS)[number]["id"]
