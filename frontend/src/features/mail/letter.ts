/**
 * What a letter becomes on screen and what an answer to it starts as (D369,
 * D370). Plain functions, tested without mounting anything.
 */
import DOMPurify from "dompurify"

import type { MailAddress, MailMessage } from "@/client"

const REMOTE = /^(?:https?:)?\/\//i
const EXTERNAL_HREF = /^(?:https?|mailto|tel):/i

/**
 * Tags a letter may not bring in at all. `style` is kept, unlike a Markdown
 * document's: a letter is laid out by its stylesheet, and in an iframe with
 * no scripts and a policy that loads nothing, a stylesheet only paints.
 */
const FORBIDDEN = ["script", "iframe", "frame", "object", "embed", "form", "base", "meta", "link"]

export interface LetterDocument {
  /** A whole document for the iframe's `srcdoc`. */
  srcdoc: string
  /** How many images wait for "Show images". */
  blockedImages: number
}

/**
 * The letter's HTML, cleaned and wrapped in a document whose policy loads
 * images from `data:` only, until the reader asks for the rest (D369).
 */
export function letterDocument(
  html: string,
  inlineImages: Record<string, string>,
  showRemote: boolean
): LetterDocument {
  const fragment = DOMPurify.sanitize(html, {
    WHOLE_DOCUMENT: false,
    RETURN_DOM_FRAGMENT: true,
    FORBID_TAGS: FORBIDDEN,
    ADD_TAGS: ["style"],
    ADD_ATTR: ["target"],
    ALLOW_UNKNOWN_PROTOCOLS: false,
  })
  let blockedImages = 0
  for (const image of fragment.querySelectorAll("img")) {
    const source = image.getAttribute("src")?.trim() ?? ""
    if (source.toLowerCase().startsWith("cid:")) {
      const inline = inlineImages[source.slice(4).replace(/^<|>$/g, "")]
      if (inline === undefined) image.removeAttribute("src")
      else image.setAttribute("src", inline)
    } else if (REMOTE.test(source) && !showRemote) {
      image.removeAttribute("src")
      blockedImages += 1
    }
  }
  for (const link of fragment.querySelectorAll("a")) {
    const href = link.getAttribute("href")?.trim() ?? ""
    if (EXTERNAL_HREF.test(href)) {
      link.setAttribute("target", "_blank")
      link.setAttribute("rel", "noopener noreferrer")
    } else {
      link.removeAttribute("href")
    }
  }
  const holder = document.createElement("div")
  holder.append(fragment)
  const images = showRemote ? "data: https: http:" : "data:"
  const policy = `default-src 'none'; img-src ${images}; style-src 'unsafe-inline'; font-src data:`
  const srcdoc =
    `<!doctype html><html><head><meta charset="utf-8">` +
    `<meta http-equiv="Content-Security-Policy" content="${policy}">` +
    `<base target="_blank">` +
    // A letter is laid out for paper whatever the application's theme: the
    // light scheme's own system colours, so no colour is reached for here.
    `<style>:root{color-scheme:light}body{margin:0;padding:12px;font-family:sans-serif;` +
    `font-size:14px;overflow-wrap:anywhere;color:CanvasText;background:Canvas}` +
    `img{max-width:100%;height:auto}</style>` +
    `</head><body>${holder.innerHTML}</body></html>`
  return { srcdoc, blockedImages }
}

/** The text of a letter that has only HTML, for quoting it. */
export function textOf(message: Pick<MailMessage, "text" | "html">): string {
  if (message.text !== null && message.text.trim() !== "") return message.text
  if (message.html === null) return ""
  const parsed = new DOMParser().parseFromString(
    DOMPurify.sanitize(message.html, { FORBID_TAGS: FORBIDDEN }),
    "text/html"
  )
  return (parsed.body.textContent ?? "").replace(/\n{3,}/g, "\n\n").trim()
}

export function addressText(address: MailAddress): string {
  return address.name ? `${address.name} <${address.address}>` : address.address
}

/** "a@b.c, Name <d@e.f>; g@h" as the addresses in it. */
export function parseAddresses(text: string): string[] {
  return text
    .split(/[,;\n]/)
    .map((part) => {
      const inside = /<([^>]+)>/.exec(part)
      return (inside?.[1] ?? part).trim()
    })
    .filter((one) => one !== "")
}

/** Whether a typed address looks like one, by the server's own pattern. */
export function isAddress(text: string): boolean {
  return /^[^@\s<>,;]+@[^@\s<>,;]+$/.test(text)
}

const REPLY_PREFIX = /^\s*(re|aw|sv|ответ)\s*:/i
const FORWARD_PREFIX = /^\s*(fwd?|wg|пересл)\s*:/i

export function replySubject(subject: string): string {
  return REPLY_PREFIX.test(subject) ? subject : `Re: ${subject}`
}

export function forwardSubject(subject: string): string {
  return FORWARD_PREFIX.test(subject) ? subject : `Fwd: ${subject}`
}

export type AnswerKind = "reply" | "reply_all" | "forward"

export interface Draft {
  to: string
  cc: string
  bcc: string
  subject: string
  text: string
  reply_to: { folder: string; uid: number } | null
  forward_of: { folder: string; uid: number } | null
}

export function emptyDraft(): Draft {
  return { to: "", cc: "", bcc: "", subject: "", text: "", reply_to: null, forward_of: null }
}

/**
 * What an answer or a forward starts as. `own` is the mailbox's address,
 * left out of Reply all, as every client leaves you out of your own answer.
 */
export function answerDraft(
  kind: AnswerKind,
  message: MailMessage,
  own: string,
  heading: { wrote: string; forwarded: string }
): Draft {
  const ref = { folder: message.folder, uid: message.uid }
  // The last line break would be quoted as a line of its own.
  const body = textOf(message).trimEnd()
  if (kind === "forward") {
    return {
      ...emptyDraft(),
      subject: forwardSubject(message.subject),
      text: `\n\n${heading.forwarded}\n${body}`,
      forward_of: ref,
    }
  }
  const replyTo = message.reply_to.length > 0 ? message.reply_to : message.sender ? [message.sender] : []
  const mine = own.toLowerCase()
  const notMine = (one: MailAddress) => one.address.toLowerCase() !== mine
  const to = replyTo.map((one) => one.address)
  const cc =
    kind === "reply_all"
      ? [...message.to, ...message.cc]
          .filter(notMine)
          .map((one) => one.address)
          .filter((one) => !to.includes(one))
      : []
  const quoted = body
    .split("\n")
    .map((line) => `> ${line}`)
    .join("\n")
  return {
    ...emptyDraft(),
    to: to.join(", "),
    cc: [...new Set(cc)].join(", "),
    subject: replySubject(message.subject),
    text: `\n\n${heading.wrote}\n${quoted}`,
    reply_to: ref,
  }
}
