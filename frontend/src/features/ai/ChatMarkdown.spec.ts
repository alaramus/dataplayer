import { mount } from "@vue/test-utils"
import { describe, expect, it } from "vitest"

import { MAX_RICH_BLOCK_CHARS } from "@/features/content/markdown/blocks"

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

  // The chat and the document draw every block but prose with one component;
  // the chat had its own copy, worded differently and drawn eagerly.
  it("draws what is not prose the way a document does", () => {
    const wrapper = mount(ChatMarkdown, {
      props: { text: "```echarts\n" + "x".repeat(MAX_RICH_BLOCK_CHARS + 1) + "\n```\n" },
    })
    expect(wrapper.get('[data-testid="markdown-oversized"]').text()).toBe(
      "This echarts block is too large to draw."
    )
  })

  it("shows a placeholder instead of mounting an unfinished rich block", () => {
    const wrapper = mount(ChatMarkdown, { props: { text: "```echarts\n{" } })
    expect(wrapper.get('[data-testid="ai-open-fence"]').text()).toContain("echarts")
    expect(wrapper.find('[data-testid="echarts-block"]').exists()).toBe(false)
  })
})
