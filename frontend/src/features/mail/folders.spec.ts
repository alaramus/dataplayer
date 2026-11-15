import { describe, expect, it } from "vitest"

import type { MailFolder } from "@/client"

import { firstFolder, shownFolders } from "./folders"

function folder(changes: Partial<MailFolder>): MailFolder {
  return {
    id: "x",
    name: "x",
    delimiter: "/",
    role: null,
    selectable: true,
    messages: 0,
    unseen: 0,
    ...changes,
  }
}

describe("a mailbox's folders", () => {
  it("are called by their role, or by their last name indented", () => {
    const shown = shownFolders(
      [
        folder({ id: "INBOX", name: "INBOX", role: "inbox", unseen: 3 }),
        folder({ id: "[Gmail]/Sent Mail", name: "[Gmail]/Sent Mail", role: "sent" }),
        folder({ id: "Work/2026", name: "Work/2026", unseen: null }),
      ],
      (role) => `role:${role}`
    )
    expect(shown.map((one) => [one.label, one.depth, one.unseen])).toEqual([
      ["role:inbox", 0, 3],
      ["role:sent", 0, 0],
      ["2026", 1, 0],
    ])
  })

  it("open at the inbox, else at the first that opens", () => {
    expect(firstFolder([folder({ id: "A" }), folder({ id: "INBOX", role: "inbox" })])).toBe("INBOX")
    expect(firstFolder([folder({ id: "A", selectable: false }), folder({ id: "B" })])).toBe("B")
    expect(firstFolder([])).toBeNull()
  })
})
