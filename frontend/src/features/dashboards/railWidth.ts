/**
 * How wide the dashboards rail is (D125).
 *
 * Dragged by the gap beside it, the way two workspace columns are, and held
 * narrower than the dashboard: never more than two fifths of the space, never
 * too narrow for its own buttons. The floor wins on a window so narrow that
 * both cannot hold.
 */

export {
  clampRailWidth,
  parseRailNarrow,
  parseRailWidth,
  RAIL_DEFAULT_PX,
  RAIL_MAX_SHARE,
  RAIL_MIN_PX,
  RAIL_NARROW_PX,
} from "@/shared/workspace/railWidth"
