import { t } from "@/shared/i18n"

type FetchResource = (input: RequestInfo | URL) => Promise<Pick<Response, "blob" | "ok">>

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = () => reject(reader.error ?? new Error("Could not encode export resource"))
    reader.readAsDataURL(blob)
  })
}

async function embedCssUrls(
  css: string,
  baseUrl: string,
  pageOrigin: string,
  fetchResource: FetchResource
): Promise<string> {
  const matches = [...css.matchAll(/url\(\s*(['"]?)([^'")]+)\1\s*\)/gi)]
  const replacements = new Map<string, string>()
  const unique = matches.filter(
    (match, index) => matches.findIndex((candidate) => candidate[0] === match[0]) === index
  )
  await Promise.all(
    unique.map(async (match) => {
      const token = match[0]
      const rawUrl = match[2]?.trim() ?? ""
      if (rawUrl === "" || rawUrl.startsWith("data:") || rawUrl.startsWith("#")) return
      let timeout = 0
      try {
        const resourceUrl = new URL(rawUrl, baseUrl)
        if (resourceUrl.protocol !== "blob:" && resourceUrl.origin !== pageOrigin) return
        const response = await Promise.race([
          fetchResource(resourceUrl),
          new Promise<never>((_resolve, reject) => {
            timeout = window.setTimeout(() => reject(new Error("Export resource timed out")), 4000)
          }),
        ])
        if (response.ok) {
          replacements.set(token, `url("${await blobToDataUrl(await response.blob())}")`)
        }
      } catch {
        // An optional local font keeps its original URL when it cannot be embedded.
      } finally {
        window.clearTimeout(timeout)
      }
    })
  )
  let result = css
  replacements.forEach((replacement, token) => {
    result = result.split(token).join(replacement)
  })
  return result
}

async function collectStyles(source: Document, fetchResource: FetchResource): Promise<string> {
  const styles: string[] = []
  for (const sheet of Array.from(source.styleSheets)) {
    try {
      const css = Array.from(sheet.cssRules)
        .map((rule) => rule.cssText)
        .join("\n")
      styles.push(
        await embedCssUrls(css, sheet.href ?? source.baseURI, source.location.origin, fetchResource)
      )
    } catch {
      // Cross-origin stylesheets are neither read nor fetched for an export.
    }
  }
  return styles.join("\n")
}

function cleanClone(sourceRoot: HTMLElement): HTMLElement {
  const clone = sourceRoot.cloneNode(true) as HTMLElement
  clone.querySelectorAll("script, [data-export-exclude]").forEach((element) => element.remove())
  clone
    .querySelectorAll("mark[data-search-highlight]")
    .forEach((mark) => mark.replaceWith(...mark.childNodes))
  clone.querySelectorAll<HTMLElement>(".markdown-search-active").forEach((element) => {
    element.classList.remove("markdown-search-active")
  })
  clone.querySelectorAll<HTMLElement>('[tabindex="-1"]').forEach((element) => {
    element.removeAttribute("tabindex")
  })
  return clone
}

async function embedLocalImages(
  sourceRoot: HTMLElement,
  clone: HTMLElement,
  fetchResource: FetchResource
): Promise<void> {
  const sourceImages = Array.from(sourceRoot.querySelectorAll("img"))
  const clonedImages = Array.from(clone.querySelectorAll("img"))
  for (let index = 0; index < sourceImages.length; index += 1) {
    const source = sourceImages[index]
    const target = clonedImages[index]
    if (source === undefined || target === undefined) continue
    const rawUrl = source.currentSrc || source.src
    if (rawUrl === "" || rawUrl.startsWith("data:")) continue
    try {
      const resourceUrl = new URL(rawUrl, sourceRoot.ownerDocument.baseURI)
      const pageOrigin = sourceRoot.ownerDocument.location.origin
      if (resourceUrl.protocol !== "blob:" && resourceUrl.origin !== pageOrigin) continue
      const response = await fetchResource(resourceUrl)
      if (!response.ok) throw new Error("The local image could not be read for export")
      target.src = await blobToDataUrl(await response.blob())
    } catch {
      // A short-lived preview URL is worse than no source in a saved file: it
      // would look portable, then break as soon as its ticket expires.
      target.removeAttribute("src")
      target.setAttribute("data-export-image-error", "")
      target.setAttribute("title", t("content.markdown.export_file.image_not_embedded"))
    }
    target.removeAttribute("data-relative-reference")
    target.removeAttribute("data-relative-loading")
  }
}

/** One inert, standalone copy of the rendered and already-sanitised document. */
export async function createRenderedHtml(
  sourceRoot: HTMLElement,
  title: string,
  fetchResource: FetchResource = (input) => fetch(input)
): Promise<string> {
  const sourceDocument = sourceRoot.ownerDocument
  const clone = cleanClone(sourceRoot)
  await embedLocalImages(sourceRoot, clone, fetchResource)
  const styles = await collectStyles(sourceDocument, fetchResource)
  const bodyClass = escapeHtml(sourceDocument.body.className)
  const language = escapeHtml(sourceDocument.documentElement.lang || "en")
  return `<!doctype html>
<html lang="${language}">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; font-src data:; img-src data: https: http:">
  <title>${escapeHtml(title)}</title>
  <style>${styles}
    body { margin: 0; padding: clamp(16px, 4vw, 48px); }
    .exported-document { width: min(1100px, 100%); margin: 0 auto; }
    .exported-document .markdown-panel__document { overflow: visible; padding: 0; }
    @media print { body { padding: 0; } }
  </style>
</head>
<body class="${bodyClass}">
  <main class="exported-document">${clone.outerHTML}</main>
</body>
</html>`
}

export function createHtmlFileName(documentName: string): string {
  const base = documentName.trim().replace(/\.(?:md|markdown)$/i, "") || "document"
  return `${base}.html`
}

/** Print the inert export, not the surrounding workspace application. */
export function printRenderedHtml(html: string): void {
  const frame = document.createElement("iframe")
  frame.setAttribute("title", t("content.markdown.export_file.printable"))
  frame.style.position = "fixed"
  frame.style.width = "1px"
  frame.style.height = "1px"
  frame.style.opacity = "0"
  frame.style.pointerEvents = "none"
  frame.onload = () => {
    const printable = frame.contentWindow
    if (printable === null) {
      frame.remove()
      return
    }
    printable.addEventListener("afterprint", () => frame.remove(), { once: true })
    printable.focus()
    printable.print()
    window.setTimeout(() => frame.remove(), 60_000)
  }
  frame.srcdoc = html
  document.body.append(frame)
}

/** Give eager async blocks a bounded opportunity to finish before cloning. */
export async function waitForDocumentRender(root: HTMLElement): Promise<void> {
  const deadline = Date.now() + 5000
  while (Date.now() < deadline) {
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()))
    const pending = root.querySelector(".deferred-block__placeholder")
    const charts = Array.from(root.querySelectorAll('[data-testid="echarts-figure"]'))
    const chartPending = charts.some((chart) => chart.querySelector("svg") === null)
    const diagrams = Array.from(root.querySelectorAll('[data-testid="mermaid-figure"]'))
    const diagramPending = diagrams.some((diagram) => diagram.querySelector("svg") === null)
    if (pending === null && !chartPending && !diagramPending) return
    await new Promise<void>((resolve) => window.setTimeout(resolve, 60))
  }
}
