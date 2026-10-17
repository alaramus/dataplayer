import type { TimescaleStatistics } from "@/client"
import type { Fact } from "@/features/summary/facts"
import { t } from "@/shared/i18n"

export function statisticsFacts(statistics: TimescaleStatistics, aggregate: boolean): Fact[] {
  const facts: Fact[] = []
  const size = statistics.size
  if (size.kind === "unavailable") {
    facts.push({ label: t("summary.statistics.size"), value: size.reason })
  } else {
    facts.push(
      {
        label: t("summary.statistics.size_scope"),
        value: aggregate
          ? t("summary.statistics.scope_aggregate")
          : t("summary.statistics.scope_hypertable"),
      },
      { label: t("summary.statistics.total_bytes"), value: size.total_bytes },
      { label: t("summary.statistics.table_bytes"), value: size.table_bytes },
      { label: t("summary.statistics.index_bytes"), value: size.index_bytes },
      { label: t("summary.statistics.toast_bytes"), value: size.toast_bytes },
    )
  }
  const compression = statistics.compression
  if (compression.kind === "unavailable") {
    facts.push({ label: t("summary.statistics.compression"), value: compression.reason })
    return facts
  }
  facts.push(
    {
      label: t("summary.statistics.measurements"),
      value: aggregate
        ? t("summary.statistics.measurements_aggregate")
        : t("summary.statistics.measurements_hypertable"),
    },
    { label: t("summary.statistics.report_chunks"), value: compression.total_chunks },
    { label: t("summary.statistics.compressed_chunks"), value: compression.number_compressed_chunks },
  )
  for (const [field, label] of [
    ["before_compression_total_bytes", "summary.statistics.before_total"],
    ["after_compression_total_bytes", "summary.statistics.after_total"],
    ["before_compression_table_bytes", "summary.statistics.before_table"],
    ["after_compression_table_bytes", "summary.statistics.after_table"],
    ["before_compression_index_bytes", "summary.statistics.before_index"],
    ["after_compression_index_bytes", "summary.statistics.after_index"],
    ["before_compression_toast_bytes", "summary.statistics.before_toast"],
    ["after_compression_toast_bytes", "summary.statistics.after_toast"],
  ] as const) {
    facts.push({ label: t(label), value: compression[field] ?? t("summary.statistics.not_reported") })
  }
  return facts
}
