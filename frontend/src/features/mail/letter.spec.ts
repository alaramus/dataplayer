import { describe, expect, it } from "vitest"

import type { MailMessage } from "@/client"

import {
  answerDraft,
  forwardSubject,
  letterDocument,
  parseAddresses,
  replySubject,
  textOf,
} from "./letter"

function message(changes: Partial<MailMessage> = {}): MailMessage {
  return {
    folder: "INBOX",
    uid: 7,
    subject: "Numbers",
    sender: { name: "Carol", address: "carol@example.com" },
    to: [
      { name: "", address: "me@example.com" },
      { name: "Bob", address: "bob@example.com" },
    ],
    cc: [{ name: "", address: "dave@example.com" }],
    reply_to: [],
    date: null,
    message_id: "<n@example.com>",
    flagged: false,
    answered: false,
    text: "line one\nline two",
    html: null,
    inline_images: {},
    attachments: [],
    ...changes,
  }
}

const HEADING = { wrote: "Carol wrote:", forwarded: "Forwarded:" }

describe("a letter's HTML", () => {
  it("loses its scripts, frames, forms and handlers", () => {
    const { srcdoc } = letterDocument(
      `<p onclick="x()">Hi</p><script>alert(1)</script><iframe src="https://x"></iframe><form><input></form>`,
      {},
      false
    )
    expect(srcdoc).toContain("<p>Hi</p>")
    expect(srcdoc).not.toContain("script>alert")
    expect(srcdoc).not.toContain("<iframe")
    expect(srcdoc).not.toContain("<form")
    expect(srcdoc).not.toContain("onclick")
  })

  it("holds remote images back and counts them until asked", () => {
    const html = `<img src="https://tracker.example/p.gif"><img src="//cdn.example/a.png">`
    const blocked = letterDocument(html, {}, false)
    expect(blocked.blockedImages).toBe(2)
    expect(blocked.srcdoc).not.toContain("tracker.example")
    expect(blocked.srcdoc).toContain("img-src data:;")
    const shown = letterDocument(html, {}, true)
    expect(shown.blockedImages).toBe(0)
    expect(shown.srcdoc).toContain("tracker.example")
    expect(shown.srcdoc).toContain("img-src data: https: http:")
  })

  it("draws inline images from what came with the letter", () => {
    const { srcdoc, blockedImages } = letterDocument(
      `<img src="cid:logo@x">`,
      { "logo@x": "data:image/png;base64,AAAA" },
      false
    )
    expect(blockedImages).toBe(0)
    expect(srcdoc).toContain('src="data:image/png;base64,AAAA"')
  })

  it("opens external links in a new tab and drops the rest", () => {
    const { srcdoc } = letterDocument(
      `<a href="https://example.com">out</a><a href="javascript:alert(1)">bad</a>`,
      {},
      false
    )
    expect(srcdoc).toContain('target="_blank"')
    expect(srcdoc).toContain('rel="noopener noreferrer"')
    expect(srcdoc).not.toContain("javascript:")
  })
})

describe("addresses", () => {
  it("are read out of what a person types", () => {
    expect(parseAddresses("a@b.c, Name <d@e.f>; g@h\n")).toEqual(["a@b.c", "d@e.f", "g@h"])
    expect(parseAddresses(" ,, ")).toEqual([])
  })
})

describe("answers", () => {
  it("prefix a subject once", () => {
    expect(replySubject("Numbers")).toBe("Re: Numbers")
    expect(replySubject("RE: Numbers")).toBe("RE: Numbers")
    expect(forwardSubject("Fwd: x")).toBe("Fwd: x")
    expect(forwardSubject("x")).toBe("Fwd: x")
  })

  it("reply to the sender and quote the text", () => {
    const draft = answerDraft("reply", message(), "me@example.com", HEADING)
    expect(draft.to).toBe("carol@example.com")
    expect(draft.cc).toBe("")
    expect(draft.text).toContain("Carol wrote:\n> line one\n> line two")
    expect(draft.reply_to).toEqual({ folder: "INBOX", uid: 7 })
    expect(draft.forward_of).toBeNull()
  })

  it("reply to Reply-To when the letter names one", () => {
    const draft = answerDraft(
      "reply",
      message({ reply_to: [{ name: "", address: "list@example.com" }] }),
      "me@example.com",
      HEADING
    )
    expect(draft.to).toBe("list@example.com")
  })

  it("reply to everyone but yourself", () => {
    const draft = answerDraft("reply_all", message(), "ME@example.com", HEADING)
    expect(draft.to).toBe("carol@example.com")
    expect(draft.cc).toBe("bob@example.com, dave@example.com")
  })

  it("forward with nobody chosen yet and the original named", () => {
    const draft = answerDraft("forward", message(), "me@example.com", HEADING)
    expect(draft.to).toBe("")
    expect(draft.subject).toBe("Fwd: Numbers")
    expect(draft.forward_of).toEqual({ folder: "INBOX", uid: 7 })
    expect(draft.reply_to).toBeNull()
  })

  it("quote a letter that has only HTML by its text", () => {
    expect(textOf(message({ text: null, html: "<p>Hello <b>you</b></p><script>x</script>" }))).toBe(
      "Hello you"
    )
  })
})
