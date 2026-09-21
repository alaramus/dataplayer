import { mount } from "@vue/test-utils"
import { QIcon, Quasar } from "quasar"
import { describe, expect, it } from "vitest"
import { defineComponent } from "vue"

import AppPairs from "./AppPairs.vue"
import AppPairsRow from "./AppPairsRow.vue"

function mountPairs(template: string) {
  return mount(defineComponent({ components: { AppPairs, AppPairsRow }, template }), {
    global: { plugins: [Quasar] },
  })
}

describe("AppPairs", () => {
  it("heads the pairs and points each one the way it was told", () => {
    const wrapper = mountPairs(`
      <AppPairs arrow="back">
        <template #from>Column here</template>
        <template #to>Filled from</template>
        <template #aside>1 of 2 filled</template>
        <AppPairsRow><template #from>id</template><template #to>source_id</template></AppPairsRow>
        <AppPairsRow idle><template #from>notes</template><template #to>Left as it is</template></AppPairsRow>
      </AppPairs>`)
    const legend = wrapper.get(".app-pairs__legend")
    expect(legend.text()).toContain("Column here")
    expect(legend.get(".app-pairs__aside").text()).toBe("1 of 2 filled")
    expect(wrapper.classes()).not.toContain("app-pairs--extra")
    const rows = wrapper.findAll(".app-pairs-row")
    expect(rows.map((row) => row.classes().includes("app-pairs-row--idle"))).toEqual([false, true])
    expect(wrapper.findAllComponents(QIcon).map((icon) => icon.props("name"))).toEqual(["arrow_back", "arrow_back"])
  })

  it("gives a third column to the legend and every row when asked for one", () => {
    const wrapper = mountPairs(`
      <AppPairs>
        <template #from>In the file</template>
        <template #to>Column in the new table</template>
        <template #extra>Type</template>
        <AppPairsRow>
          <template #from>id</template><template #to>id</template><template #extra>integer</template>
        </AppPairsRow>
      </AppPairs>`)
    expect(wrapper.classes()).toContain("app-pairs--extra")
    expect(wrapper.get(".app-pairs-row").findAll(".app-pairs-row__cell")).toHaveLength(3)
    expect(wrapper.getComponent(QIcon).props("name")).toBe("arrow_forward")
  })
})
