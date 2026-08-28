export function toTsv(matrix: readonly (readonly (string | null)[])[]): string {
  return matrix.map((row) => row.map(tsvCell).join("\t")).join("\r\n")
}

function tsvCell(value: string | null): string {
  if (value === null) return ""
  if (!/[\t\r\n"]/u.test(value)) return value
  return `"${value.replaceAll('"', '""')}"`
}
