/**
 * A random version 4 UUID.
 *
 * Not `crypto.randomUUID`, which exists only in a secure context: a page
 * served over plain HTTP to another machine does not have it, while
 * `getRandomValues` is there everywhere. The server parses some of these as
 * UUIDs (a query's run id), so the shape is the standard one.
 */
export function newId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6]! & 0x0f) | 0x40
  bytes[8] = (bytes[8]! & 0x3f) | 0x80
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("")
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
