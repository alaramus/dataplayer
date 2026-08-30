import { afterEach, describe, expect, it, vi } from "vitest"

import { client } from "@/client/client.gen"

import {
  filenameFromDisposition,
  saveBrowserDownload,
  saveNativeDownload,
} from "./download"

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
  client.setConfig({ baseURL: "" })
})

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

  it("follows a stored export without creating a browser blob", () => {
    vi.useFakeTimers()
    client.setConfig({ baseURL: "https://api.example.test" })
    const create = vi.spyOn(URL, "createObjectURL")
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined)

    saveNativeDownload("/api/v1/connectors/export-downloads/a-ticket")

    const link = document.querySelector<HTMLAnchorElement>('a[href*="a-ticket"]')
    expect(link?.href).toBe(
      "https://api.example.test/api/v1/connectors/export-downloads/a-ticket"
    )
    expect(click).toHaveBeenCalledOnce()
    expect(create).not.toHaveBeenCalled()

    vi.runAllTimers()
    expect(document.querySelector('a[href*="a-ticket"]')).toBeNull()
  })
})
