import { inject, ref } from "vue"
import type { InjectionKey, Ref } from "vue"

/**
 * Whether the dashboards space is the one shown.
 *
 * Kept alive behind another space so the windows it opened stay (D125), it
 * reads nothing meanwhile: its widgets' queries stand still and catch up when
 * it is shown again. A widget outside the space — one in a window — is always
 * on screen, which is what the default says.
 */
export const dashboardsShownKey: InjectionKey<Readonly<Ref<boolean>>> = Symbol("dashboards shown")

export function useDashboardsShown(): Readonly<Ref<boolean>> {
  return inject(dashboardsShownKey, ref(true))
}
