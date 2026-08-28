import { defineComponent, Fragment, h, ref } from "vue"
import type { Component } from "vue"

import { provideWindows, useWindows, WindowHost } from "@/shared/windows"

/** A production-shaped floating-window host for focused component tests. */
export function withWindowHost(component: Component, props: Record<string, unknown>): Component {
  return defineComponent({
    name: "WindowTestRoot",
    setup: (_props, { expose }) => {
      const windows = useWindows()
      provideWindows(windows)
      const child = ref<{ reload?: () => Promise<void> } | null>(null)
      expose({ reload: () => child.value?.reload?.() })
      return () =>
        h(Fragment, [h(component, { ...props, ref: child }), h(WindowHost, { context: windows.context })])
    },
  })
}
