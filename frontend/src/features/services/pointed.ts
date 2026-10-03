import { readonly, ref } from "vue"

/**
 * A service somebody asked to see — a search hit — waiting for the services
 * tool at the foot of the screen to point at it (D143, D205). A module ref:
 * the tool may not be mounted until the press that asked opens it.
 */
const pending = ref<string | null>(null)

export const pointedService = readonly(pending)

export function pointAtService(serviceId: string): void {
  pending.value = serviceId
}

export function takePointedService(): string | null {
  const serviceId = pending.value
  pending.value = null
  return serviceId
}
