import { describe, expect, it } from "vitest"

import { MAX_FIELD_FILE_BYTES, droppedFile, readFieldFile } from "./fieldFile"

const PEM = "-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"

describe("readFieldFile", () => {
  it("gives the text of the file as it is, lines and all", async () => {
    expect(await readFieldFile(new File([PEM], "ca.pem"), "CA certificate")).toBe(PEM)
  })

  it("drops the byte-order mark a Windows editor saves a key with", async () => {
    const bytes = new Uint8Array([0xef, 0xbb, 0xbf, ...new TextEncoder().encode('{"type":"x"}')])
    expect(await readFieldFile(new File([bytes], "key.json"), "Key")).toBe('{"type":"x"}')
  })

  it("refuses a binary file, which could never be the text of the field", async () => {
    // A DER certificate begins with a SEQUENCE tag and is not UTF-8.
    const der = new File([new Uint8Array([0x30, 0x82, 0x01, 0x0a, 0xff, 0x00])], "ca.der")
    await expect(readFieldFile(der, "CA certificate")).rejects.toThrow("CA certificate")
  })

  it("refuses a file longer than the field takes", async () => {
    await expect(readFieldFile(new File([PEM], "ca.pem"), "CA certificate", 10)).rejects.toThrow("10")
  })

  it("refuses a file far larger than any certificate before reading it", async () => {
    const huge = new File([new Uint8Array(MAX_FIELD_FILE_BYTES + 1)], "disk.img")
    await expect(readFieldFile(huge, "Client key")).rejects.toThrow("Client key")
  })
})

describe("droppedFile", () => {
  it("takes one file and nothing when there are several", () => {
    const one = new File([PEM], "ca.pem")
    expect(droppedFile({ files: [one] } as unknown as DataTransfer)).toBe(one)
    expect(droppedFile({ files: [one, one] } as unknown as DataTransfer)).toBeNull()
    expect(droppedFile(null)).toBeNull()
  })
})
