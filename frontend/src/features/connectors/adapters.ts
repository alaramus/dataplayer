/**
 * How a source type is drawn in a list.
 *
 * A plain function so it is tested without mounting anything, the way
 * `nodes.ts` and `rows.ts` are. An unknown type gets a generic glyph rather
 * than nothing: the registry lives in the backend and gains entries without
 * the frontend being redeployed, so a missing entry here is a normal state.
 *
 * The drawings are files rather than glyphs of an icon font — a source type is
 * a product with a logo, and no font has those. Quasar loads one with the
 * `img:` prefix. They are served from `public/`, so a type that gains an icon
 * needs a file and a line here, nothing else.
 */
const ICONS: Record<string, string> = {
  postgres: "img:/icons/services/postgresql.svg",
  file: "img:/icons/services/folder.svg",
}

export const UNKNOWN_ADAPTER_ICON = "cable"

export function adapterIcon(adapterType: string): string {
  return ICONS[adapterType] ?? UNKNOWN_ADAPTER_ICON
}
