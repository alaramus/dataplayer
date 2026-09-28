/**
 * Where the rail of dashboards draws a line between its groups, wide or narrow.
 *
 * Only between two groups that both show something: with no dashboards, or
 * only shared ones, a line stood under nothing, right below the head.
 */
export interface RailRules {
  /** Between one's own dashboards and the ones shared with one. */
  beforeShared: boolean
  /**
   * Between the dashboards of either kind and the sources, in the narrow rail.
   * The wide one always rules off its sources, folded at its foot.
   */
  beforeSources: boolean
}

export function railRules(own: number, shared: number): RailRules {
  return { beforeShared: own > 0 && shared > 0, beforeSources: own + shared > 0 }
}
