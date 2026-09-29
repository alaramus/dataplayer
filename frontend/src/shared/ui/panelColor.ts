import type { CSSProperties } from "vue"

/**
 * What one chosen color turns into: a surface, the text that stays readable
 * on it, and the same color said quietly.
 *
 * Three and not one, because a color is used for two different jobs. A tab is
 * filled with it and needs to know what to write on it; a row that is merely
 * open is marked by a wash of it and keeps the text color it had, the way
 * `--dp-selected-quiet` is the quiet half of `--dp-selected`. Both are decided
 * here so that a screen asks for the meaning and never mixes a color itself.
 */
export function panelColorStyle(color: string | null | undefined): CSSProperties {
  if (!color || color.length !== 7 || !/^#[\da-f]{6}$/i.test(color)) return {}
  const red = Number.parseInt(color.slice(1, 3), 16)
  const green = Number.parseInt(color.slice(3, 5), 16)
  const blue = Number.parseInt(color.slice(5, 7), 16)
  const channel = (byte: number) => {
    const value = byte / 255
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  }
  const luminance = channel(red) * 0.2126 + channel(green) * 0.7152 + channel(blue) * 0.0722
  const blackContrast = (luminance + 0.05) / 0.05
  const whiteContrast = 1.05 / (luminance + 0.05)
  return {
    "--dp-panel-background": color,
    "--dp-panel-foreground": blackContrast >= whiteContrast ? "#000000" : "#ffffff",
    // Translucent rather than mixed with a surface: what it is laid over is
    // the panel's own background, and the wash has to work on either theme.
    "--dp-panel-quiet": `rgba(${String(red)}, ${String(green)}, ${String(blue)}, 0.5)`,
  }
}
