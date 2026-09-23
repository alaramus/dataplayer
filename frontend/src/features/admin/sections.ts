import { appIcons } from "@/shared/ui/icons"

/**
 * A list rather than a page, because there will be more than one section.
 * Nothing here knows what a section shows: the page maps an id onto a
 * component, and this decides only what is offered and in what order.
 */

export interface AdminSection {
  /** The last part of the address: `/admin/users`. */
  id: string
  title: string
  /** What it is for, under the title in the list. */
  summary: string
  icon: string
}

export const ADMIN_SECTIONS: readonly AdminSection[] = [
  {
    id: "users",
    title: "Users",
    summary: "Who has an account, and who administers this installation",
    icon: appIcons.group,
  },
]

/** The section an address names, or the first one when it names none of them. */
export function sectionFor(id: string | undefined): AdminSection {
  const found = ADMIN_SECTIONS.find((section) => section.id === id)
  // Never null: an address that names nothing is a person who typed `/admin`,
  // and the answer to that is the first section rather than an empty screen.
  return found ?? ADMIN_SECTIONS[0]!
}
