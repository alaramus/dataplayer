import type { TimescaleStatistics } from "@/client"
import type { Fact } from "@/features/summary/facts"

export function statisticsFacts(statistics: TimescaleStatistics, aggregate: boolean): Fact[] {
  const facts: Fact[] = []
  const size = statistics.size
  if (size.kind === "unavailable") {
    facts.push({ label: "TimescaleDB size", value: size.reason })
  } else {
    facts.push(
      {
        label: "Size scope",
        value: aggregate ? "Aggregate materialization" : "Hypertable including chunks",
      },
      { label: "Total storage (bytes)", value: size.total_bytes },
      { label: "Table storage (bytes)", value: size.table_bytes },
      { label: "Index storage (bytes)", value: size.index_bytes },
      { label: "TOAST storage (bytes)", value: size.toast_bytes },
    )
  }
  const compression = statistics.compression
  if (compression.kind === "unavailable") {
    facts.push({ label: "Compression statistics", value: compression.reason })
    return facts
  }
  facts.push(
    {
      label: "Compression measurements",
      value: aggregate
        ? "Recorded materialization sizes at compression; not current storage"
        : "Recorded sizes at compression; not current storage",
    },
    { label: "Chunks in compression report", value: compression.total_chunks },
    { label: "Compressed chunks", value: compression.number_compressed_chunks },
  )
  for (const [field, label] of [
    ["before_compression_total_bytes", "Before compression, total (bytes)"],
    ["after_compression_total_bytes", "After compression, total (bytes)"],
    ["before_compression_table_bytes", "Before compression, table (bytes)"],
    ["after_compression_table_bytes", "After compression, table (bytes)"],
    ["before_compression_index_bytes", "Before compression, indexes (bytes)"],
    ["after_compression_index_bytes", "After compression, indexes (bytes)"],
    ["before_compression_toast_bytes", "Before compression, TOAST (bytes)"],
    ["after_compression_toast_bytes", "After compression, TOAST (bytes)"],
  ] as const) {
    facts.push({ label, value: compression[field] ?? "Not reported" })
  }
  return facts
}
