/**
 * Reading an element a test expects to be there.
 *
 * Indexing is `T | undefined` under noUncheckedIndexedAccess, and writing `?.`
 * in a test turns a missing element into a wrong value: the assertion then
 * reports `undefined` instead of saying that nothing was produced.
 */
export function first<T>(items: readonly T[]): T {
  return at(items, 0)
}

export function at<T>(items: readonly T[], index: number): T {
  const item = items[index]
  if (item === undefined) {
    throw new Error(`expected an element at ${index}, got a list of ${items.length}`)
  }
  return item
}

/** The same, for a record keyed by something a test expects to be present. */
export function keyed<T>(record: Record<string, T>, key: string): T {
  const item = record[key]
  if (item === undefined) {
    throw new Error(`expected a "${key}" entry, got ${Object.keys(record).join(", ")}`)
  }
  return item
}
