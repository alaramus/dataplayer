/**
 * How a source type is drawn in a list. A plain function, tested without
 * mounting anything. An unknown type gets a generic glyph rather than nothing:
 * the registry lives in the backend and gains entries without the frontend
 * being redeployed, so a missing entry here is a normal state.
 *
 * The drawings are files rather than glyphs of an icon font — a source type is
 * a product with a logo, and no font has those. Quasar loads one with the
 * `img:` prefix, served from `public/`.
 */
const ICONS: Record<string, string> = {
  postgres: "img:/icons/services/postgresql.svg",
  mysql: "img:/icons/services/mysql.svg",
  redis: "img:/icons/services/redis.svg",
  file: "img:/icons/services/folder.svg",
  ssh: "img:/icons/services/ssh.svg",
}

export const UNKNOWN_ADAPTER_ICON = "cable"

export function adapterIcon(adapterType: string): string {
  return ICONS[adapterType] ?? UNKNOWN_ADAPTER_ICON
}

/**
 * The glyph beside a category in the catalog's sidebar.
 *
 * A glyph and not a logo: a category is a heading, not a product, so this is
 * an icon-font name rather than a file. What a category is *called* comes from
 * the server with the type — only the drawing is decided here, for the same
 * reason the logos above are.
 */
const CATEGORY_ICONS: Record<string, string> = {
  sql: "table_chart",
  keyvalue: "key",
  files: "folder",
}

export const UNKNOWN_CATEGORY_ICON = "category"

export function categoryIcon(category: string): string {
  return CATEGORY_ICONS[category] ?? UNKNOWN_CATEGORY_ICON
}
