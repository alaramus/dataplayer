import { t } from "@/shared/i18n"

/** Elapsed time while a run is live, fixed at its recorded finish afterwards. */
export function runDuration(
  run: { created_at?: string | null; finished_at?: string | null },
  now: number
): string {
  if (!run.created_at) return ""
  const end = run.finished_at ? Date.parse(run.finished_at) : now
  const seconds = Math.max(0, Math.round((end - Date.parse(run.created_at)) / 1000))
  return t("ai.conversation.seconds", { n: seconds })
}
