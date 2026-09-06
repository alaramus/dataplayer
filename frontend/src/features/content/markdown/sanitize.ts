/**
 * Every string that becomes DOM in a rendered document passes through here.
 *
 * Two levels, and the second is not a repeat of the first: raw HTML written by
 * the document's author is cleaned at token level with `style` forbidden, and
 * the assembled result is cleaned again keeping inline `style` only inside
 * KaTeX, whose layout is generated as inline styles. A document can arrive
 * from somebody else's connection through a read grant, so remote resources
 * are refused unless the reader asks for them (D50).
 */
import DOMPurify from "dompurify"

/** Links that lead somewhere outside this application, and may be followed. */
const EXTERNAL_HREF = /^(?:https?|mailto|tel):/i
const INLINE_IMAGE = /^data:image\/(?:png|gif|jpe?g|webp);base64,/i
const REMOTE = /^(?:https?:)?\/\//i

/** Tags no document may introduce, whatever it writes. */
const FORBIDDEN = ["style", "iframe", "object", "embed", "form", "button"]

export interface SanitizeOptions {
  allowRemoteImages?: boolean
}

export function isRemoteSource(value: string): boolean {
  return REMOTE.test(value.trim())
}

function harden(root: ParentNode, options: SanitizeOptions): void {
  for (const link of root.querySelectorAll("a")) {
    const href = link.getAttribute("href")?.trim() ?? ""
    if (href.startsWith("#")) continue
    if (EXTERNAL_HREF.test(href)) {
      // A document lives inside a workspace panel: following a link in place
      // would take the whole application with it.
      link.setAttribute("target", "_blank")
      link.setAttribute("rel", "noopener noreferrer")
      continue
    }
    // The panel resolves this through the source's path and catalog contracts.
    // It must not become a browser navigation to the DataPlayer origin first.
    link.removeAttribute("href")
    if (href) link.setAttribute("data-relative-link", href)
  }

  for (const image of root.querySelectorAll("img")) {
    const source = image.getAttribute("src")?.trim() ?? ""
    if (source && isRemoteSource(source) && options.allowRemoteImages !== true) {
      // Kept as an attribute rather than dropped silently: the panel counts
      // these and says that something was not fetched.
      image.removeAttribute("src")
      image.setAttribute("data-remote-blocked", "")
    } else if (source && !isRemoteSource(source) && !INLINE_IMAGE.test(source)) {
      // A same-origin-looking path belongs to the source, not this web app.
      // The document panel resolves it to an opaque node before requesting a
      // verified D49 preview ticket.
      image.removeAttribute("src")
      image.setAttribute("data-relative-source", source)
    }
    image.setAttribute("loading", "lazy")
    image.setAttribute("referrerpolicy", "no-referrer")
  }

  for (const input of root.querySelectorAll("input")) {
    if (input.getAttribute("type") === "checkbox") input.setAttribute("disabled", "")
    else input.remove()
  }
}

function hardened(html: string, options: SanitizeOptions): DocumentFragment {
  const template = document.createElement("template")
  template.innerHTML = html
  harden(template.content, options)
  return template.content
}

/** Author-written raw HTML, cleaned before it joins anything the renderer made. */
export function sanitizeFragment(html: string, options: SanitizeOptions = {}): string {
  const clean = DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    FORBID_TAGS: FORBIDDEN,
    FORBID_ATTR: ["style", "srcset"],
  })
  const content = hardened(clean, options)
  const holder = document.createElement("div")
  holder.append(content)
  return holder.innerHTML
}

/**
 * The whole rendered document. KaTeX positions fractions, indices and matrices
 * with generated inline styles and is unreadable without them, so `style`
 * survives inside `.katex` and nowhere else.
 */
export function sanitizeDocument(html: string, options: SanitizeOptions = {}): string {
  const clean = DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    FORBID_TAGS: FORBIDDEN,
    FORBID_ATTR: ["srcset"],
  })
  const content = hardened(clean, options)
  for (const element of content.querySelectorAll<HTMLElement>("[style]")) {
    if (!element.closest(".katex")) element.removeAttribute("style")
  }
  const holder = document.createElement("div")
  holder.append(content)
  return holder.innerHTML
}

/**
 * An `svg` fence, and everything Mermaid draws. Mermaid positions its own nodes
 * with inline styles, so it asks for them; a hand-written fence does not get
 * them, because nothing in a document needs to style itself that way.
 */
export function sanitizeSvg(svg: string, options: { allowStyles?: boolean } = {}): string {
  return DOMPurify.sanitize(svg, {
    USE_PROFILES: { svg: true, svgFilters: true },
    FORBID_TAGS: ["script", "foreignObject", "iframe", "object", "embed", "audio", "video"],
    FORBID_ATTR: options.allowStyles === true ? [] : ["style"],
  })
}
