import type { CSSProperties } from "vue"

/** The supplied background and whichever text color has the higher contrast. */
export function panelColorStyle(color: string | null | undefined): CSSProperties {
  if (!color || color.length !== 7 || !/^#[\da-f]{6}$/i.test(color)) return {}
  const channel = (start: number) => {
    const value = Number.parseInt(color.slice(start, start + 2), 16) / 255
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  }
  const luminance = channel(1) * 0.2126 + channel(3) * 0.7152 + channel(5) * 0.0722
  const blackContrast = (luminance + 0.05) / 0.05
  const whiteContrast = 1.05 / (luminance + 0.05)
  return {
    "--dp-panel-background": color,
    "--dp-panel-foreground": blackContrast >= whiteContrast ? "#000000" : "#ffffff",
  }
}
