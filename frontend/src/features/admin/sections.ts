import type { PageSection } from "@/shared/ui"
import { appIcons } from "@/shared/ui/icons"

/** What Administration offers, in order; the page maps each id onto its body. */
export const ADMIN_SECTIONS = [
  {
    id: "users",
    title: "Users",
    summary: "Who has an account, and who administers this installation",
    icon: appIcons.group,
  },
] as const satisfies readonly [PageSection, ...PageSection[]]

export type AdminSectionId = (typeof ADMIN_SECTIONS)[number]["id"]
