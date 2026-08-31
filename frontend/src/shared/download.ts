import { client } from "@/client/client.gen"

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

/** Hand one bounded blob to the browser as a file to save. */
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

/** Follow a ticket so the browser streams bytes without building a JavaScript Blob. */
export function saveNativeDownload(downloadUrl: string): void {
  const link = document.createElement("a")
  link.href = client.buildUrl({ url: downloadUrl })
  document.body.append(link)
  link.click()
  setTimeout(() => link.remove(), 0)
}
