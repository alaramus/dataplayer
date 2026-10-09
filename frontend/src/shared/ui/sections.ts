/**
 * One entry of a page made of sections, Administration and Preferences: what
 * the list beside the body offers. Nothing here knows what a section shows;
 * the page maps an id onto a component.
 */
export interface PageSection {
  /** The last part of the address: `/preferences/connections`. */
  id: string
  title: string
  /** What it is for, under the title in the list. */
  summary: string
  icon: string
}

/**
 * The section an address names, or the first one when it names none of them.
 *
 * Never null: an address that names nothing is a person who typed the page's
 * own address, and the answer to that is the first section rather than an
 * empty screen.
 */
export function sectionOf<L extends readonly [PageSection, ...PageSection[]]>(
  sections: L,
  id: string | undefined
): L[number] {
  return sections.find((section) => section.id === id) ?? sections[0]
}
