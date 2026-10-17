import type { CatalogNode } from "@/features/catalog/nodes"
import { t } from "@/shared/i18n"

export interface RelativeTarget {
  node: CatalogNode
  fragment: string
}

type LoadPath = (connectorId: string, nodeId: string) => Promise<CatalogNode[]>
type LoadChildren = (connectorId: string, nodeId: string | null) => Promise<CatalogNode[]>

interface ParsedReference {
  absolute: boolean
  segments: string[]
  fragment: string
}

function decodePart(value: string, part: "fragment" | "path"): string {
  try {
    return decodeURIComponent(value)
  } catch {
    throw new Error(t(`content.markdown.relative.${part}_encoding`))
  }
}

function parseReference(reference: string): ParsedReference {
  const value = reference.trim()
  if (/^[a-z][a-z0-9+.-]*:/i.test(value) || value.startsWith("//")) {
    throw new Error(t("content.markdown.relative.not_relative"))
  }
  const hashAt = value.indexOf("#")
  const beforeFragment = hashAt < 0 ? value : value.slice(0, hashAt)
  const fragment = hashAt < 0 ? "" : decodePart(value.slice(hashAt + 1), "fragment")
  const queryAt = beforeFragment.indexOf("?")
  const path = queryAt < 0 ? beforeFragment : beforeFragment.slice(0, queryAt)
  const absolute = path.startsWith("/")
  const rawSegments = path.slice(absolute ? 1 : 0).split("/")
  if (rawSegments.some((part, index) => part === "" && index < rawSegments.length - 1)) {
    throw new Error(t("content.markdown.relative.empty_segment"))
  }
  const segments = rawSegments.filter((part) => part !== "").map((part) => decodePart(part, "path"))
  if (segments.some((part) => part.includes("/") || part.includes("\\") || part.includes("\0"))) {
    throw new Error(t("content.markdown.relative.invalid_segment"))
  }
  return { absolute, segments, fragment }
}

/**
 * Resolve a document reference without ever taking a source node id apart.
 *
 * The current path and every child are source-issued objects. `..` moves over
 * that chain; an ordinary segment selects a source-issued child by its name.
 */
export async function resolveRelativeTarget(
  connectorId: string,
  currentNodeId: string,
  reference: string,
  loadPath: LoadPath,
  loadChildren: LoadChildren
): Promise<RelativeTarget> {
  const parsed = parseReference(reference)
  const currentPath = await loadPath(connectorId, currentNodeId)
  const current = currentPath.at(-1)
  if (current === undefined || current.id !== currentNodeId) {
    throw new Error(t("content.markdown.relative.no_source_path"))
  }
  if (parsed.segments.length === 0 && !parsed.absolute) {
    return { node: current, fragment: parsed.fragment }
  }

  const ancestors = parsed.absolute ? [] : currentPath.slice(0, -1)
  let target: CatalogNode | undefined
  for (const segment of parsed.segments) {
    if (segment === ".") continue
    if (segment === "..") {
      if (ancestors.length === 0) {
        throw new Error(t("content.markdown.relative.leaves_root"))
      }
      target = ancestors.pop()
      continue
    }
    const parent = ancestors.at(-1)?.id ?? null
    const matches = (await loadChildren(connectorId, parent)).filter(
      (node) => node.name === segment
    )
    if (matches.length === 0) throw new Error(t("content.markdown.relative.no_node", { name: segment }))
    if (matches.length > 1) throw new Error(t("content.markdown.relative.ambiguous", { name: segment }))
    target = matches[0]
    if (target === undefined) throw new Error(t("content.markdown.relative.no_node", { name: segment }))
    ancestors.push(target)
  }

  target ??= ancestors.at(-1)
  if (target === undefined) {
    throw new Error(t("content.markdown.relative.root_not_document"))
  }
  return { node: target, fragment: parsed.fragment }
}
