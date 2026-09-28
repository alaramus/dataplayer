/**
 * The page a link between the guide's pages names: `source-redis.md` names
 * `source-redis`. Anything else is not a page, and the window says so rather
 * than letting the browser leave the application.
 */
export function pageOfLink(reference: string): string | null {
  const found = /^([a-z0-9]+(?:-[a-z0-9]+)*)\.md(?:#.*)?$/.exec(reference.trim())
  return found?.[1] ?? null
}
