import { onBeforeUnmount, ref, watch } from "vue"
import type { Ref } from "vue"

import type { Hit, SearchRequest } from "@/client"
import { askWhole } from "@/features/search/stream"
import { DEBOUNCE_MS, MIN_CHARACTERS } from "@/features/search/words"

type ProviderKey = Extract<NonNullable<SearchRequest["only"]>[number], { kind: "objects" }>["provider"]

/**
 * What one provider finds for the words typed into a window of its own.
 *
 * The type catalog asks the search's source-type provider rather than
 * matching types itself (D197). Debounced and aborted like the field: a newer
 * word ends the older ask, here and on the server. `null` while there is
 * nothing to ask yet; the last answer is kept while the next is on its way, so
 * a list does not empty between two keys.
 */
export function useProviderHits(
  words: Ref<string>,
  provider: ProviderKey
): { hits: Ref<Hit[] | null> } {
  const hits = ref<Hit[] | null>(null)
  let controller: AbortController | null = null
  let timer: ReturnType<typeof setTimeout> | null = null

  function cancel() {
    controller?.abort()
    controller = null
    if (timer !== null) clearTimeout(timer)
    timer = null
  }

  async function ask(typed: string) {
    const own = new AbortController()
    controller = own
    try {
      const lines = await askWhole(
        {
          words: typed,
          mode: "typing",
          lane: "types",
          only: [{ kind: "objects", provider }],
        },
        own.signal
      )
      if (own.signal.aborted) return
      hits.value = lines.flatMap((line) => (line.type === "cell" ? line.hits : []))
    } catch {
      if (!own.signal.aborted) hits.value = []
    }
  }

  watch(words, (value) => {
    cancel()
    const typed = value.trim()
    if (typed.length < MIN_CHARACTERS) {
      hits.value = null
      return
    }
    timer = setTimeout(() => void ask(typed), DEBOUNCE_MS)
  })

  onBeforeUnmount(cancel)
  return { hits }
}
