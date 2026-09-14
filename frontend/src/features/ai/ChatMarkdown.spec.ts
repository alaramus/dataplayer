import { mount } from "@vue/test-utils"
import { describe, expect, it } from "vitest"

import ChatMarkdown from "./ChatMarkdown.vue"

describe("ChatMarkdown", () => {
  it("never requests remote images or turns relative links into navigation", () => {
    const wrapper = mount(ChatMarkdown, {
      props: { text: "![secret](https://example.test/leak?q=value) [local](orders/42)" },
    })
    const image = wrapper.get("img")
    expect(image.attributes("src")).toBeUndefined()
    expect(image.attributes()).toHaveProperty("data-remote-blocked")
    expect(wrapper.get("a").attributes("href")).toBeUndefined()
  })

  it("shows a placeholder instead of mounting an unfinished rich block", () => {
    const wrapper = mount(ChatMarkdown, { props: { text: "```echarts\n{" } })
    expect(wrapper.get('[data-testid="ai-open-fence"]').text()).toContain("echarts")
    expect(wrapper.find('[data-testid="echarts-block"]').exists()).toBe(false)
  })
})
