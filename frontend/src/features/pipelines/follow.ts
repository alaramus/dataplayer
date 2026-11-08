import type { FollowedLinkPublic, FollowState } from "@/client"
import type { GraphEdgeTone } from "@/shared/graph/model"
import { t } from "@/shared/i18n"

/**
 * A pipeline following its topics (D315), as the canvas and the panel say it:
 * plain functions of what the server answered, so they are tested without a
 * screen.
 */

/** How often the screen asks again while a pipeline follows. */
export const FOLLOW_POLL_MS = 2_000

/** A followed link's line while its pipeline follows: what it is doing now. */
export function followTone(entry: FollowedLinkPublic | undefined): GraphEdgeTone | undefined {
  if (entry === undefined) return undefined
  if (entry.state === "retrying") return "error"
  if (entry.state === "carrying") return "info"
  return undefined
}

/** Each link's entry of the newest following, by link. */
export function followedLinks(state: FollowState | undefined): Map<string, FollowedLinkPublic> {
  return new Map((state?.links ?? []).map((one) => [one.link_id, one]))
}

/** The panel's line about a followed link while its pipeline follows. */
export function followWords(entry: FollowedLinkPublic | undefined, at: (iso: string) => string): string {
  if (entry === undefined || (entry.carried === 0 && entry.state !== "retrying")) {
    return t("pipelines.follow.waiting")
  }
  if (entry.state === "retrying") {
    return t("pipelines.follow.retrying", { reason: entry.last_error ?? "", count: entry.failures })
  }
  return entry.last_at
    ? t("pipelines.follow.carried_at", { count: entry.carried, at: at(entry.last_at) })
    : t("pipelines.follow.carried", { count: entry.carried })
}
