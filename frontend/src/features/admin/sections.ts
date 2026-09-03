/**
 * What administering this installation is made of.
 *
 * A list rather than a page, because there will be more than one of them: the
 * accounts are the first thing an administrator needs and not the last, and a
 * screen built around exactly one section is a screen that has to be taken
 * apart to gain a second.
 *
 * Nothing here knows what a section shows. The page maps an id onto a
 * component; this decides only what is offered, in what order, and which one
 * an address names.
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
    icon: "group",
  },
]

/** The section an address names, or the first one when it names none of them. */
export function sectionFor(id: string | undefined): AdminSection {
  const found = ADMIN_SECTIONS.find((section) => section.id === id)
  // Never null: an address that names nothing is a person who typed `/admin`,
  // and the answer to that is the first section rather than an empty screen.
  return found ?? ADMIN_SECTIONS[0]!
}
