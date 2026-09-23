import outlinedSymbols from "@quasar/extras/material-symbols-outlined/icons.json"

const available = new Set(outlinedSymbols)

const keyOf = (icon: string) =>
  `symOutlined${icon.replace(/(^|_)([a-z])/g, (_, _separator: string, letter: string) => letter.toUpperCase())}`

/** Map the application's ligatures to the installed Symbols Outlined font. */
export function symbolIcon(icon: string): { icon: string } | undefined {
  if (!/^[a-z][a-z0-9_]*$/.test(icon)) return undefined
  return available.has(keyOf(icon)) ? { icon: `sym_o_${icon}` } : undefined
}
