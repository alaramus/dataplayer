import { defineStore } from "pinia"
import { ref } from "vue"

import { serverStorageKey } from "@/shared/servers/context"

/**
 * Which space fills the screen: Data, Dashboards or the application agent
 * (D125, D141).
 *
 * Pinia, because the server knows nothing about it (D6). Remembered per
 * browser and per server, like the layout it stands beside.
 */
export const SPACES = ["data", "dashboards", "ai"] as const
export type Space = (typeof SPACES)[number]

const KEY = "dataplayer-space"

function stored(): Space {
  try {
    const value = localStorage.getItem(serverStorageKey(KEY))
    return SPACES.find((space) => space === value) ?? "data"
  } catch {
    return "data"
  }
}

export const useSpaceStore = defineStore("space", () => {
  const current = ref<Space>(stored())

  function show(space: Space) {
    current.value = space
    try {
      localStorage.setItem(serverStorageKey(KEY), space)
    } catch {
      // A browser that refuses storage still switches; it just forgets.
    }
  }

  return { current, show }
})
