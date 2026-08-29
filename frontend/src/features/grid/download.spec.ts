import { describe, expect, it, vi } from "vitest"

import { filenameFromDisposition, saveBrowserDownload } from "./download"

describe("a CSV browser download", () => {
  it("uses the UTF-8 attachment name returned by the server", () => {
    expect(
      filenameFromDisposition(
        "attachment; filename=report.csv; filename*=UTF-8''PostgreSQL%20classes.csv",
        "fallback.csv"
      )
    ).toBe("PostgreSQL classes.csv")
  })

  it("clicks a link that is in the document, and only then releases it", () => {
    vi.useFakeTimers()
    const create = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:page")
    const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)
    let connectedAtClick: boolean | null = null
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(function (this: HTMLAnchorElement) {
        connectedAtClick = this.isConnected
      })
    const blob = new Blob(["id\n1\n"], { type: "text/csv" })

    saveBrowserDownload(blob, "page.csv")

    expect(create).toHaveBeenCalledWith(blob)
    expect(click).toHaveBeenCalledOnce()
    // A detached link is not followed by every browser, and an object URL
    // released in the same tick can cancel the download it started.
    expect(connectedAtClick).toBe(true)
    expect(revoke).not.toHaveBeenCalled()

    vi.runAllTimers()

    expect(revoke).toHaveBeenCalledWith("blob:page")
    expect(document.querySelector("a[download]")).toBeNull()
    vi.useRealTimers()
  })
})
