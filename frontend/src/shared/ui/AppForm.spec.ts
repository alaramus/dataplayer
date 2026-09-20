import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { defineComponent } from "vue"
import { describe, expect, it } from "vitest"

import AppFileInput from "./AppFileInput.vue"
import AppForm from "./AppForm.vue"
import AppInput from "./AppInput.vue"
import AppNumberInput from "./AppNumberInput.vue"
import AppSelect from "./AppSelect.vue"

describe("form composition", () => {
  it("keeps labels and native field contracts when fields have no floating labels", async () => {
    const wrapper = mount(defineComponent({
      components: { AppForm, AppInput, AppNumberInput, AppSelect, AppFileInput },
      template: `<AppForm>
        <AppInput model-value="" label="Host" error="Required" data-testid="host" />
        <AppNumberInput :model-value="5432" label="Port" />
        <AppSelect model-value="prefer" label="SSL mode" :options="['prefer', 'require']" />
        <AppFileInput :model-value="null" label="Key file" />
      </AppForm>`,
    }), { global: { plugins: [Quasar] } })
    expect(wrapper.text()).toContain("Host")
    expect(wrapper.text()).toContain("Port")
    expect(wrapper.text()).toContain("SSL mode")
    const input = wrapper.get('[data-testid="host"]')
    expect(input.attributes("aria-label")).toBe("Host")
    expect(input.attributes("aria-invalid")).toBe("true")
    expect(wrapper.get(`#${input.attributes("aria-describedby")}`).text()).toBe("Required")
    await input.setValue("db")
    expect(wrapper.getComponent(AppInput).emitted("update:modelValue")?.at(-1)).toEqual(["db"])
    expect(wrapper.get('input[type="number"]').attributes("aria-label")).toBe("Port")
    expect(wrapper.get('[role="combobox"]').attributes("aria-label")).toBe("SSL mode")
    expect(wrapper.get('input[type="file"]').attributes("aria-label")).toBe("Key file")
    wrapper.unmount()
  })
})
