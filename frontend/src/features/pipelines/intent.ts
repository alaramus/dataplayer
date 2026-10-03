import { readonly, ref } from "vue"

/**
 * A pipeline asked for from elsewhere — a search hit — waiting for the
 * pipelines space to open it, as a dashboard waits for its own.
 *
 * Watched rather than read once: the space is kept alive once it has been
 * shown, and its setup does not run again for a later request.
 */
const pending = ref<string | null>(null)

export const pipelineIntent = readonly(pending)

export function setPipelineIntent(pipelineId: string): void {
  pending.value = pipelineId
}

export function takePipelineIntent(): string | null {
  const pipelineId = pending.value
  pending.value = null
  return pipelineId
}
