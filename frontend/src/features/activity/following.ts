import type { ComputedRef, Ref } from "vue"
import { computed } from "vue"

import type { JobPublic } from "@/client"
import { isWorking } from "@/features/services/jobs"
import { t } from "@/shared/i18n"
import type { AttentionItem } from "@/shared/notifications"

import { isRecord, text } from "./transfers"

/**
 * A pipeline following its topics, as its job records it
 * (app/pipelines/follow.py, D315): the links it follows and what each
 * carried. Read field by field; a record that is not recognised is drawn as
 * an ordinary job.
 */

/** Failures in a row after which a followed link needs a person. */
export const NEEDS_YOU_AFTER = 10

export interface FollowedLinkRecord {
  linkId: string
  title: string
  carried: number
  failures: number
  lastError: string | null
}

export interface FollowRecord {
  pipelineName: string
  links: FollowedLinkRecord[]
}

function linkOf(value: unknown): FollowedLinkRecord | null {
  if (!isRecord(value)) return null
  const linkId = text(value.link_id)
  const title = text(value.title)
  if (linkId === null || title === null) return null
  if (typeof value.carried !== "number" || typeof value.failures !== "number") return null
  return { linkId, title, carried: value.carried, failures: value.failures, lastError: text(value.last_error) }
}

export function followOf(job: JobPublic): FollowRecord | null {
  if (job.kind !== "pipeline.follow" || !isRecord(job.parameters)) return null
  const name = text(job.parameters.pipeline_name)
  const links = job.parameters.links
  if (name === null || !Array.isArray(links)) return null
  const read = links.map(linkOf)
  if (read.some((one) => one === null)) return null
  return { pipelineName: name, links: read as FollowedLinkRecord[] }
}

export function carriedOf(record: FollowRecord): number {
  return record.links.reduce((sum, one) => sum + one.carried, 0)
}

/** Each followed link that keeps failing, while its pipeline follows (D115). */
export function followingAttention(jobs: Ref<JobPublic[]>): ComputedRef<AttentionItem[]> {
  return computed(() =>
    jobs.value.flatMap((job) => {
      const record = isWorking(job) ? followOf(job) : null
      if (record === null) return []
      return record.links
        .filter((one) => one.failures >= NEEDS_YOU_AFTER)
        .map((one): AttentionItem => ({
          id: `follow:${job.id}:${one.linkId}`,
          tone: "error",
          title: t("activity.following.failing", { name: record.pipelineName, link: one.title }),
          detail: t("activity.following.failing_detail", { count: one.failures, reason: one.lastError ?? "" }),
          at: Date.parse(job.started_at ?? job.created_at) || Date.now(),
          action: null,
          // It goes when the link carries again; waving it away would hide a link that does not.
          dismiss: null,
        }))
    })
  )
}
