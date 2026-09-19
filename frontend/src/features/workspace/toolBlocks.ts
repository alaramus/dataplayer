import type { Component } from "vue"

import SpaceSwitch from "@/features/dashboards/SpaceSwitch.vue"
import ServicesCommand from "@/features/services/ServicesCommand.vue"
import TerminalCommand from "@/features/terminals/TerminalCommand.vue"

import CommandBar from "./CommandBar.vue"
import TabGroupList from "./TabGroupList.vue"
import TabGroupSave from "./TabGroupSave.vue"
import type { BlockSeat } from "./toolRails"
import type { TabGroupLibrary } from "./useTabGroups"

/** What a rail knows that a block may need. */
export interface RailContext {
  groups: TabGroupLibrary
  /**
   * The side of the screen the rail stands on. Not `onLeft`: a prop named
   * on + a capital is taken for a listener when it is bound from an object,
   * and never arrives.
   */
  side: "left" | "right"
}

export interface ToolBlock extends BlockSeat {
  component: Component
  /** The block's props, from what the rail it stands on knows. */
  props: (rail: RailContext) => Record<string, unknown>
  /** Several buttons, framed as one group under the pointer. */
  framed?: boolean
}

/**
 * Everything the side rails can hold (workspace.md, Tool rails).
 *
 * A new block is an entry here and nothing else: the rails draw it, the drag
 * and drop moves it, and a stored arrangement that predates it seats it at
 * its home. The save button and the list of tab groups are two blocks, so
 * each can be carried on its own.
 */
export const TOOL_BLOCKS: readonly ToolBlock[] = [
  { id: "spaces", home: "left-top", framed: true, component: SpaceSwitch, props: () => ({ iconOnly: true }) },
  { id: "queries", home: "left-top", component: CommandBar, props: () => ({ iconOnly: true }) },
  { id: "services", home: "left-bottom", component: ServicesCommand, props: () => ({ iconOnly: true }) },
  {
    id: "terminals",
    home: "left-bottom",
    beside: "services",
    component: TerminalCommand,
    props: () => ({ iconOnly: true }),
  },
  { id: "groups-save", home: "right-top", component: TabGroupSave, props: (rail) => ({ groups: rail.groups }) },
  {
    id: "groups-list",
    home: "right-top",
    beside: "groups-save",
    component: TabGroupList,
    props: (rail) => ({ groups: rail.groups, side: rail.side }),
  },
]
