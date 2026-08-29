export function filenameFromDisposition(disposition: string | undefined, fallback: string): string {
  if (disposition === undefined) return fallback
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1]
  if (encoded !== undefined) {
    try {
      return decodeURIComponent(encoded)
    } catch {
      return fallback
    }
  }
  return /filename="([^"]+)"/i.exec(disposition)?.[1] ?? fallback
}

/**
 * Hand one blob to the browser as a file to save.
 *
 * Two details are not decoration. A link that is not in the document is not
 * followed by every browser, and an object URL revoked in the same tick as the
 * click can cancel the download that click just started. Both leave a button
 * that silently does nothing, and neither is visible to a test that only
 * asserts `click` was called, so the test beside this asserts both directly.
 */
export function saveBrowserDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = filename
  document.body.append(link)
  link.click()
  setTimeout(() => {
    link.remove()
    URL.revokeObjectURL(url)
  }, 0)
}
