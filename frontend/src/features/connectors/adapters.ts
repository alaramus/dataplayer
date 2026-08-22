/**
 * How a source type is drawn in a list.
 *
 * A plain function so it is tested without mounting anything, the way
 * `treeNodes.ts` and `rows.ts` are. An unknown type gets a generic icon rather
 * than nothing: the registry lives in the backend and gains entries without
 * the frontend being redeployed, so a missing entry here is a normal state.
 */
const ICONS: Record<string, string> = {
  postgres: "storage",
  file: "folder",
}

export const UNKNOWN_ADAPTER_ICON = "cable"

export function adapterIcon(adapterType: string): string {
  return ICONS[adapterType] ?? UNKNOWN_ADAPTER_ICON
}
