import type { Sort } from "@/client"

export function toggleSingleSort(sort: readonly Sort[], column: string): Sort[] {
  const current = sort.find((item) => item.column === column)
  if (current === undefined) return [{ column, descending: false }]
  if (current.descending !== true) return [{ column, descending: true }]
  return []
}

export function toggleMultiSort(sort: readonly Sort[], column: string): Sort[] {
  const index = sort.findIndex((item) => item.column === column)
  if (index === -1) return [...sort, { column, descending: false }]

  const current = sort[index]
  if (current === undefined) return [...sort]
  if (current.descending === true) return sort.filter((_, itemIndex) => itemIndex !== index)

  return sort.map((item, itemIndex) =>
    itemIndex === index ? { ...item, descending: true } : item
  )
}

export function moveSort(sort: readonly Sort[], index: number, delta: -1 | 1): Sort[] {
  const target = index + delta
  if (index < 0 || index >= sort.length || target < 0 || target >= sort.length) {
    return [...sort]
  }

  const result = [...sort]
  const item = result[index]
  const other = result[target]
  if (item === undefined || other === undefined) return result
  result[index] = other
  result[target] = item
  return result
}
