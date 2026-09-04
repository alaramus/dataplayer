import type { DetectedFramework } from "@/client"
import type { ListNode } from "@/features/catalog/nodes"

/** Show every source-issued hint from the schemas the reader chose. */
export function frameworksOf(groups: ListNode[], selectedIds: string[]): DetectedFramework[] {
  const selected = new Set(selectedIds)
  const detected = new Map<DetectedFramework["id"], DetectedFramework>()
  for (const group of groups) {
    if (!selected.has(group.id)) continue
    for (const framework of group.frameworks ?? []) {
      detected.set(framework.id, framework)
    }
  }
  return [...detected.values()].sort((a, b) => a.title.localeCompare(b.title))
}

/** The same literal text as typing in the catalog filter, never a query. */
export function toggleFrameworkFilter(current: string, framework: DetectedFramework): string {
  return current === framework.table_filter ? "" : framework.table_filter
}
