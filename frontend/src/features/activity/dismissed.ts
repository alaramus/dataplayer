import { shallowRef } from "vue"
import type { Ref } from "vue"

import { serverStorageKey } from "@/shared/servers/context"

import { RECENT_FOR } from "./endings"

/**
 * The jobs whose ending a person has waved away, in Recent or in Needs you.
 *
 * Kept in this browser (D181): an ending is read again from the server at
 * every poll and after every reload, and one waved away must not come back.
 * An id is kept a little longer than an ending stays recent, and then dropped.
 */

const KEY = "dataplayer-activity-dismissed-jobs"
const KEPT_FOR = 2 * RECENT_FOR

type Stored = Record<string, number>

function read(storage: Storage, now: number): Stored {
  try {
    const parsed: unknown = JSON.parse(storage.getItem(serverStorageKey(KEY)) ?? "{}")
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) return {}
    return Object.fromEntries(
      Object.entries(parsed as Record<string, unknown>).filter(
        (entry): entry is [string, number] => typeof entry[1] === "number" && now - entry[1] <= KEPT_FOR
      )
    )
  } catch {
    return {}
  }
}

export interface DismissedJobs {
  ids: Ref<ReadonlySet<string>>
  dismiss: (jobId: string) => void
}

export function createDismissedJobs(
  storage: Storage = localStorage,
  now: () => number = () => Date.now()
): DismissedJobs {
  let stored = read(storage, now())
  const ids = shallowRef<ReadonlySet<string>>(new Set(Object.keys(stored)))

  function dismiss(jobId: string) {
    if (ids.value.has(jobId)) return
    stored = { ...stored, [jobId]: now() }
    ids.value = new Set([...ids.value, jobId])
    try {
      storage.setItem(serverStorageKey(KEY), JSON.stringify(stored))
    } catch {
      // A browser that refuses storage still hides it for this page.
    }
  }

  return { ids, dismiss }
}
