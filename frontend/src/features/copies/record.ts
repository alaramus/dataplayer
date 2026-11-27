import type { QueryClient } from "@tanstack/vue-query"

import { CopiesService } from "@/client"
import { copiesKey } from "@/features/copies/api"
import { onCopied } from "@/shared/clipboard"
import { useAuthStore } from "@/stores/auth"

// The server keeps 65 536 characters of a copy (copies.MAX_CHARS) and cuts the
// rest. One more than that is sent, which is how it knows to say it cut: a
// whole grid copied would otherwise travel megabytes only to be dropped.
const SENT_CHARS = 65_537
const DETAIL_CHARS = 200

/**
 * Keep every copy the application makes in the copy history (D460).
 *
 * Quiet on failure: the text is on the clipboard already, which is what the
 * person asked for, and a toast about the history would be noise on every copy
 * while the server is away.
 */
export function recordCopies(queryClient: QueryClient): void {
  onCopied((text, origin) => {
    if (!useAuthStore().isLoggedIn) return
    void CopiesService.recordCopy({
      body: {
        text: text.slice(0, SENT_CHARS),
        source: origin.from,
        detail: origin.detail ? origin.detail.slice(0, DETAIL_CHARS) : null,
      },
    })
      .then(() => queryClient.invalidateQueries({ queryKey: copiesKey }))
      .catch(() => undefined)
  })
}
