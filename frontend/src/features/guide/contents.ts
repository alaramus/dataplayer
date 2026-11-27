import type { GuidePageInfo, Hit, Segment } from "@/client"

/**
 * The Help Center's left column: the guide's pages under their sections, or
 * what a search found. Plain functions, tested without mounting anything.
 * The order is the server's, and so is what matches (D183, D202).
 */

export type GuideSection = GuidePageInfo["section"]

export interface ContentsGroup {
  section: GuideSection
  pages: GuidePageInfo[]
}

/** The pages under their sections, each in the order the server listed it. */
export function groupedContents(pages: readonly GuidePageInfo[]): ContentsGroup[] {
  const groups: ContentsGroup[] = []
  for (const page of pages) {
    const last = groups.at(-1)
    if (last?.section === page.section) last.pages.push(page)
    else groups.push({ section: page.section, pages: [page] })
  }
  return groups
}

export interface FoundPage {
  key: string
  title: string
  /** Where the words were found, the words marked; empty when the title matched. */
  excerpt: Segment[]
}

/** The guide's pages among the hits of a search, in the order it ranked them. */
export function foundPages(hits: readonly Hit[]): FoundPage[] {
  return hits.flatMap((hit) => {
    if (hit.target.kind !== "object" || hit.target.object_type !== "guide_page") return []
    const excerpt = hit.match.field === "name" ? [] : hit.match.excerpt
    return [{ key: hit.target.object_id, title: hit.title, excerpt }]
  })
}
