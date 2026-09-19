import { computed } from "vue"

import { useAdapterTypes, useConnectors } from "@/features/connectors/api"

import { terminalCandidates } from "./terminals"

/** The connections a terminal can be opened on, as the rail, the head and the panel ask. */
export function useTerminalCandidates() {
  const connectors = useConnectors()
  const types = useAdapterTypes()
  return computed(() =>
    terminalCandidates(connectors.data.value?.data ?? [], types.data.value ?? [])
  )
}
