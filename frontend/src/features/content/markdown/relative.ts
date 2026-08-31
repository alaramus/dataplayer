import type { CatalogNode } from "@/features/catalog/nodes"

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

function decodePart(value: string, label: string): string {
  try {
    return decodeURIComponent(value)
  } catch {
    throw new Error(`This relative ${label} has invalid percent encoding`)
  }
}

function parseReference(reference: string): ParsedReference {
  const value = reference.trim()
  if (/^[a-z][a-z0-9+.-]*:/i.test(value) || value.startsWith("//")) {
    throw new Error("This is not a relative source reference")
  }
  const hashAt = value.indexOf("#")
  const beforeFragment = hashAt < 0 ? value : value.slice(0, hashAt)
  const fragment = hashAt < 0 ? "" : decodePart(value.slice(hashAt + 1), "fragment")
  const queryAt = beforeFragment.indexOf("?")
  const path = queryAt < 0 ? beforeFragment : beforeFragment.slice(0, queryAt)
  const absolute = path.startsWith("/")
  const rawSegments = path.slice(absolute ? 1 : 0).split("/")
  if (rawSegments.some((part, index) => part === "" && index < rawSegments.length - 1)) {
    throw new Error("This relative path contains an empty segment")
  }
  const segments = rawSegments.filter((part) => part !== "").map((part) => decodePart(part, "path"))
  if (segments.some((part) => part.includes("/") || part.includes("\\") || part.includes("\0"))) {
    throw new Error("This relative path contains an invalid segment")
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
    throw new Error("The open document no longer has a source path")
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
        throw new Error("This relative path leaves the connection root")
      }
      target = ancestors.pop()
      continue
    }
    const parent = ancestors.at(-1)?.id ?? null
    const matches = (await loadChildren(connectorId, parent)).filter(
      (node) => node.name === segment
    )
    if (matches.length === 0) throw new Error(`No node named ${segment} exists here`)
    if (matches.length > 1) throw new Error(`More than one node is named ${segment} here`)
    target = matches[0]
    if (target === undefined) throw new Error(`No node named ${segment} exists here`)
    ancestors.push(target)
  }

  target ??= ancestors.at(-1)
  if (target === undefined) {
    throw new Error("The connection root is not a document node")
  }
  return { node: target, fragment: parsed.fragment }
}
