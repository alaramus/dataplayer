import { mount } from "@vue/test-utils"
import { Quasar } from "quasar"
import { afterEach, describe, expect, it } from "vitest"
import { computed, reactive } from "vue"

import { forgetDesign, registerDesign } from "./design"
import { emptyDraft, newCheck, newTerm } from "./draft"
import PredicateField from "./PredicateField.vue"

afterEach(() => forgetDesign("predicate-field-test"))

describe("compact predicate field", () => {
  it("opens from the keyboard, edits its own draft and keeps the edit when collapsed", async () => {
    const draft = reactive(emptyDraft("text"))
    const check = newCheck()
    check.predicate.terms.push(newTerm(draft.columns[0]!.id))
    draft.checks.push(check)
    registerDesign("predicate-field-test", {
      draft,
      options: computed(() => null),
      abilities: computed(() => ({})),
      columnChoices: computed(() =>
        draft.columns.map((column) => ({ label: column.name, value: column.id }))
      ),
      typeChoices: computed(() => []),
      types: computed(() => []),
      functions: computed(() => []),
      databases: computed(() => false),
    })
    const wrapper = mount(PredicateField, {
      global: { plugins: [Quasar] },
      props: {
        designId: "predicate-field-test",
        owner: "check",
        ownerId: check.id,
        testid: "condition",
        label: "Expression",
      },
    })
    const field = wrapper.get('[data-testid="condition-field"]')
    expect(field.attributes("aria-expanded")).toBe("false")
    await field.trigger("keydown", { key: "Enter" })
    expect(field.attributes("aria-expanded")).toBe("true")
    await wrapper.get('input[aria-label="Value"]').setValue("paid")
    await field.trigger("keydown", { key: "Enter" })
    expect((field.element as HTMLInputElement).value).toBe("id = 'paid'")
    expect(draft.checks[0]?.predicate.terms[0]?.value).toBe("paid")
    wrapper.unmount()
  })
})
