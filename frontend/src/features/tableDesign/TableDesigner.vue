<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue"

import type { TablePlan } from "@/client"
import { messageOf } from "@/shared/api/errors"
import {
  AppBanner,
  AppButton,
  AppInput,
  AppSection,
  AppSpinner,
  useConfirm,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

import { usePlanTable, useTableDesignOptions } from "./api"
import ColumnInspector from "./ColumnInspector.vue"
import ConstraintInspector from "./ConstraintInspector.vue"
import DesignNavigation from "./DesignNavigation.vue"
import { forgetDesign, newDesignId, registerDesign } from "./design"
import {
  dependents,
  emptyDraft,
  newCheck,
  newColumn,
  newForeignKey,
  newIndex,
  tally,
  toDefinition,
  withoutColumn,
  worthPlanning,
} from "./draft"
import type { Draft, DraftSection } from "./draft"
import ForeignKeyInspector from "./ForeignKeyInspector.vue"
import IndexInspector from "./IndexInspector.vue"
import TableOptionsInspector from "./TableOptionsInspector.vue"

/**
 * Design a table object by object, review what it becomes, then create it.
 *
 * Two steps in one window (D117). The first is the editor; **Review SQL**
 * replaces it with the script and the one button that creates anything, so
 * deciding to create is a step of its own rather than a button under the form.
 */
const props = defineProps<{
  modelValue: boolean
  connectorId: string
  /** The schema it is created in, as the catalog issued it. */
  nodeId: string
  nodeLabel: string
  running: boolean
  error: string
}>()

const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  run: [value: { nodeId: string; params: Record<string, unknown> }]
}>()

const confirm = useConfirm()
const connectorId = computed(() => props.connectorId)
const nodeId = computed(() => props.nodeId)
const options = useTableDesignOptions(connectorId, nodeId)
const planTable = usePlanTable()

const draft = reactive<Draft>(emptyDraft("text"))
const step = ref<"definition" | "review">("definition")
const section = ref<DraftSection>("columns")
const selected = ref(draft.columns[0]?.id ?? "")
const plan = ref<TablePlan | null>(null)
const trouble = ref("")
const touched = ref(false)

/**
 * Which draft the server is being asked about.
 *
 * A number rather than a flag: answers can arrive out of order, and one that
 * is about an older draft has to be dropped rather than shown as the current
 * plan.
 */
let asked = 0
let timer: ReturnType<typeof setTimeout> | undefined

const types = computed(() => options.data.value?.types ?? [])
const definition = computed(() => toDefinition(draft, types.value))

const columnChoices = computed(() =>
  draft.columns.map((column) => ({
    label: column.name || "(unnamed)",
    value: column.id,
  }))
)
const typeChoices = computed(() =>
  types.value.map((option) => ({ label: option.title, value: option.code }))
)

/**
 * The name this draft is known by while the window is open.
 *
 * The panels are mounted by the window host rather than under this component,
 * so they cannot inject anything from here; they are handed the name and look
 * the draft up (see `design.ts`).
 */
const designId = newDesignId()
registerDesign(designId, {
  draft,
  options: computed(() => options.data.value ?? null),
  columnChoices,
  typeChoices,
  types,
  functions: computed(() => options.data.value?.functions ?? []),
})

// The first column takes a type this server actually publishes. Seeded rather
// than hard-coded: which types exist is the source's answer, and the draft is
// built before that answer arrives.
watch(types, (published) => {
  const [first] = published
  if (first === undefined) return
  for (const column of draft.columns) {
    if (!published.some((option) => option.code === column.typeCode)) {
      column.typeCode = first.code
    }
  }
})

const problems = computed(() => plan.value?.problems ?? [])
const statements = computed(() => plan.value?.statements ?? [])
const script = computed(() =>
  statements.value.map((statement) => statement.sql).join(";\n\n") + (statements.value.length ? ";" : "")
)
/** The part of the plan the selected object is responsible for. */
const selectedSql = computed(() => {
  const own = statements.value.filter((statement) => statement.object_id === selected.value)
  const [first] = own.length > 0 ? own : statements.value
  return first?.sql ?? ""
})
const stale = computed(() => plan.value === null || plan.value.revision !== asked)
const ready = computed(
  () =>
    !stale.value &&
    plan.value !== null &&
    plan.value.fingerprint !== "" &&
    problems.value.length === 0
)
const status = computed(() => {
  if (!worthPlanning(draft)) return "Name the table and its columns"
  if (planTable.isPending.value || stale.value) return "Working out the SQL…"
  if (problems.value.length > 0) {
    return `${String(problems.value.length)} ${problems.value.length === 1 ? "problem" : "problems"} to resolve`
  }
  return `${tally(draft)} · nothing has been created`
})

function schedulePlan(): void {
  if (timer !== undefined) clearTimeout(timer)
  if (!worthPlanning(draft)) {
    plan.value = null
    return
  }
  // A pause in the typing, not a request per character. The answer is about
  // the whole definition, so asking on every keystroke would mostly be work
  // thrown away.
  timer = setTimeout(() => void ask(), 300)
}

async function ask(): Promise<void> {
  asked += 1
  const revision = asked
  trouble.value = ""
  try {
    const answer = await planTable.mutateAsync({
      connectorId: props.connectorId,
      nodeId: props.nodeId,
      definition: definition.value,
      revision,
    })
    // A late answer about an older draft is dropped rather than shown.
    if (answer.revision === asked) plan.value = answer
  } catch (cause) {
    if (revision === asked) {
      plan.value = null
      trouble.value = messageOf(cause, "The SQL could not be worked out")
    }
  }
}

watch(
  definition,
  () => {
    touched.value = true
    // Anything typed leaves the review behind: what would be created is no
    // longer what was read.
    if (step.value === "review") step.value = "definition"
    schedulePlan()
  },
  { deep: true }
)

onBeforeUnmount(() => {
  if (timer !== undefined) clearTimeout(timer)
  forgetDesign(designId)
})

function select(next: DraftSection, objectId: string): void {
  section.value = next
  selected.value = objectId
}

function add(group: DraftSection): void {
  if (group === "columns") {
    const column = newColumn(types.value[0]?.code ?? "text", draft.columns.length)
    draft.columns.push(column)
    select("columns", column.id)
    return
  }
  if (group === "indexes") {
    const index = newIndex(
      options.data.value?.index_methods?.[0]?.code ?? "btree",
      draft.columns[0]?.id ?? ""
    )
    draft.indexes.push(index)
    select("indexes", index.id)
    return
  }
  if (group === "foreign-keys") {
    const foreign = newForeignKey(props.nodeId)
    draft.foreignKeys.push(foreign)
    select("foreign-keys", foreign.id)
    return
  }
  if (group === "constraints") {
    const check = newCheck()
    draft.checks.push(check)
    select("constraints", check.id)
  }
}

async function remove(group: DraftSection, objectId: string): Promise<void> {
  if (group === "columns") {
    if (draft.columns.length === 1) return
    const affected = dependents(draft, objectId)
    if (affected.length > 0) {
      const name = draft.columns.find((column) => column.id === objectId)?.name ?? ""
      const agreed = await confirm({
        title: `Remove ${name}?`,
        message: `It is used by ${[...new Set(affected)].join(", ")}. Removing the column removes it from them too.`,
        confirmLabel: "Remove",
        danger: true,
      })
      if (!agreed) return
    }
    const next = withoutColumn(draft, objectId)
    Object.assign(draft, next)
    selected.value = draft.columns[0]?.id ?? ""
    return
  }
  if (group === "indexes") {
    draft.indexes = draft.indexes.filter((index) => index.id !== objectId)
    selected.value = draft.indexes[0]?.id ?? ""
    return
  }
  if (group === "foreign-keys") {
    draft.foreignKeys = draft.foreignKeys.filter((foreign) => foreign.id !== objectId)
    selected.value = draft.foreignKeys[0]?.id ?? ""
    return
  }
  if (group === "constraints") {
    draft.uniques = draft.uniques.filter((unique) => unique.id !== objectId)
    draft.checks = draft.checks.filter((check) => check.id !== objectId)
    selected.value = draft.uniques[0]?.id ?? draft.checks[0]?.id ?? ""
  }
}

function create(): void {
  const held = plan.value
  if (held === null || !ready.value) return
  emit("run", {
    nodeId: props.nodeId,
    params: { definition: definition.value, fingerprint: held.fingerprint },
  })
}

/** A draft nobody has touched closes without a question. */
async function mayClose(): Promise<boolean> {
  if (!touched.value || props.running) return true
  return confirm({
    title: "Discard this table?",
    message: "Nothing has been created, and the draft is not kept.",
    confirmLabel: "Discard",
    danger: true,
  })
}

async function close(): Promise<void> {
  if (await mayClose()) emit("update:modelValue", false)
}
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    size="xl"
    title="Create table"
    :subtitle="`In ${options.data.value?.schema_label || nodeLabel}`"
    :before-close="mayClose"
    data-testid="table-designer"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <AppSection gutter>
      <AppBanner
        v-if="error"
        tone="error"
        data-testid="designer-error"
      >
        {{ error }}
      </AppBanner>
      <AppBanner
        v-else-if="trouble"
        tone="warning"
      >
        {{ trouble }}
      </AppBanner>
      <AppBanner
        v-else-if="options.data.value && options.data.value.supported === false"
        tone="warning"
      >
        {{ options.data.value.reason }}
      </AppBanner>

      <div
        v-if="options.isLoading.value"
        class="designer__waiting"
      >
        <AppSpinner />
      </div>

      <!-- Step one: the definition. -->
      <template v-else-if="step === 'definition'">
        <div class="designer__identity">
          <AppInput
            v-model="draft.name"
            label="Table name"
            data-testid="table-name"
          />
          <AppInput
            v-model="draft.comment"
            label="Comment"
          />
        </div>

        <div class="designer__body">
          <DesignNavigation
            :design-id="designId"
            :section="section"
            :selected="selected"
            :problems="problems"
            @select="select"
            @add="add"
            @remove="remove"
          />

          <main
            class="designer__editor"
            data-testid="design-inspector"
          >
            <ColumnInspector
              v-if="section === 'columns'"
              :key="selected"
              :design-id="designId"
              :column-id="selected"
            />
            <IndexInspector
              v-else-if="section === 'indexes'"
              :key="selected"
              :design-id="designId"
              :index-id="selected"
            />
            <ForeignKeyInspector
              v-else-if="section === 'foreign-keys'"
              :key="selected"
              :design-id="designId"
              :foreign-key-id="selected"
              :connector-id="connectorId"
            />
            <ConstraintInspector
              v-else-if="section === 'constraints'"
              :key="selected"
              :design-id="designId"
              :constraint-id="selected"
            />
            <TableOptionsInspector
              v-else
              :design-id="designId"
            />
          </main>

          <aside
            class="designer__sql"
            aria-label="SQL preview"
            data-testid="design-sql"
          >
            <div class="designer__sql-head">
              <span>SQL</span>
              <span class="designer__sql-state">{{ stale ? "stale" : "live" }}</span>
            </div>
            <pre
              class="designer__code"
              :class="{ 'designer__code--stale': stale }"
            >{{ selectedSql }}</pre>
            <details v-if="statements.length > 1">
              <summary>Full script</summary>
              <pre class="designer__code">{{ script }}</pre>
            </details>
          </aside>
        </div>

        <ul
          v-if="problems.length"
          class="designer__problems"
          data-testid="design-problems"
        >
          <li
            v-for="(problem, at) in problems"
            :key="at"
          >
            {{ problem.message }}
          </li>
        </ul>
      </template>

      <!-- Step two: what would run, and the one button that runs it. -->
      <template v-else>
        <div
          class="designer__review"
          data-testid="design-review"
        >
          <p class="designer__target">
            {{ options.data.value?.schema_label || nodeLabel }}.{{ draft.name }} ·
            {{ statements.length }}
            {{ statements.length === 1 ? "statement" : "statements" }}
          </p>
          <pre class="designer__code designer__code--whole">{{ script }}</pre>
        </div>
      </template>
    </AppSection>

    <template #actions>
      <span
        class="designer__status"
        aria-live="polite"
        data-testid="design-status"
      >{{ step === "review" ? "Nothing has been created yet" : status }}</span>
      <AppButton
        variant="quiet"
        label="Cancel"
        @click="close"
      />
      <AppButton
        v-if="step === 'definition'"
        label="Review SQL"
        icon-right="arrow_forward"
        :disable="!ready"
        data-testid="design-review-sql"
        @click="step = 'review'"
      />
      <template v-else>
        <AppButton
          variant="quiet"
          label="Back to definition"
          icon="arrow_back"
          data-testid="design-back"
          @click="step = 'definition'"
        />
        <AppButton
          label="Create table"
          :loading="running"
          :disable="!ready"
          data-testid="design-create"
          @click="create"
        />
      </template>
    </template>
  </WindowDialog>
</template>

<style scoped>
.designer__waiting {
  display: flex;
  justify-content: center;
  padding: var(--dp-space-4);
}

.designer__identity {
  display: grid;
  grid-template-columns: minmax(160px, 1fr) minmax(160px, 2fr);
  gap: var(--dp-space-2);
}

/* Three panes on a desktop window. Below 850 the SQL moves under the
   inspector, and below 560 the navigation joins it: what a pane cannot show
   at 180 pixels is nothing anybody can read. */
.designer__body {
  display: grid;
  grid-template-columns: minmax(160px, 220px) minmax(0, 3fr) minmax(0, 2fr);
  gap: var(--dp-space-2);
  min-height: 320px;
}

.designer__editor {
  min-width: 0;
  overflow: auto;
}

.designer__sql {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-1);
  border-left: 1px solid var(--dp-border-faint);
  padding-left: var(--dp-space-2);
}

.designer__sql-head {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--dp-text-muted);
}

.designer__code {
  margin: 0;
  padding: var(--dp-space-2);
  background: var(--dp-surface-raised);
  border-radius: var(--dp-radius-panel);
  font-family: var(--dp-font-mono, monospace);
  font-size: 12px;
  line-height: 1.5;
  /* Wrapped rather than scrolled sideways: the pane beside the inspector is
     narrower than a CREATE TABLE line, and a statement read in a 300-pixel
     window through a horizontal scrollbar is not read at all. */
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

/* A plan that is being worked out again is dimmed rather than emptied: what it
   said a moment ago is still the closest thing to the truth on screen. */
.designer__code--stale {
  opacity: 0.5;
}

.designer__code--whole {
  max-height: 420px;
  overflow: auto;
}

.designer__problems {
  margin: 0;
  padding-left: var(--dp-space-4);
  color: var(--q-negative);
}

.designer__review {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
}

.designer__target {
  margin: 0;
  font-weight: 600;
}

.designer__status {
  margin-right: auto;
  color: var(--dp-text-muted);
}

@media (max-width: 850px) {
  .designer__body {
    grid-template-columns: minmax(160px, 220px) minmax(0, 1fr);
  }

  .designer__sql {
    grid-column: 1 / -1;
    border-left: 0;
    border-top: 1px solid var(--dp-border-faint);
    padding-left: 0;
    padding-top: var(--dp-space-2);
  }
}

@media (max-width: 560px) {
  .designer__body {
    grid-template-columns: minmax(0, 1fr);
  }

  .designer__identity {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
