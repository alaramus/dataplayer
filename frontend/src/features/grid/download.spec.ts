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

  it("clicks one temporary link and releases its object URL", () => {
    const create = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:page")
    const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined)
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined)
    const blob = new Blob(["id\n1\n"], { type: "text/csv" })

    saveBrowserDownload(blob, "page.csv")

    expect(create).toHaveBeenCalledWith(blob)
    expect(click).toHaveBeenCalledOnce()
    expect(revoke).toHaveBeenCalledWith("blob:page")
  })
})
