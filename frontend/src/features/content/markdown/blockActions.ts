import { copyText } from "@/shared/clipboard"
import { saveBrowserDownload } from "@/shared/download"

/**
 * What every rich block can do with itself.
 *
 * The source of a block is text and goes to the clipboard; a drawing is an SVG
 * and is handed to the browser as a file. Both go through the boundaries the
 * application already has — `shared/clipboard.ts` and `shared/download.ts` —
 * rather than touching `navigator` or building an anchor here.
 */

export async function copySource(source: string): Promise<void> {
  await copyText(source)
}

export function saveSvg(svg: string, filename: string): void {
  saveBrowserDownload(new Blob([svg], { type: "image/svg+xml" }), filename)
}

/**
 * The SVG behind a chart, out of what ECharts hands back as a data URL.
 *
 * `getDataURL` returns `data:image/svg+xml;charset=UTF-8,<encoded>`, so the
 * markup is the part after the comma, percent-decoded.
 */
export function svgFromDataUrl(dataUrl: string): string {
  const comma = dataUrl.indexOf(",")
  if (comma === -1) return ""
  try {
    return decodeURIComponent(dataUrl.slice(comma + 1))
  } catch {
    return ""
  }
}
