<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue"

import type { TablePlan } from "@/client"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import {
  AppBanner,
  AppButton,
  AppForm,
  AppInput,
  AppSelect,
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
  toDefinition,
  withoutColumn,
  worthPlanning,
} from "./draft"
import type { Draft, DraftSection } from "./draft"
import ForeignKeyInspector from "./ForeignKeyInspector.vue"
import IndexInspector from "./IndexInspector.vue"
import DesignSql from "./DesignSql.vue"
import HypertableInspector from "./HypertableInspector.vue"
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
  /** The schema the menu was opened in, as the catalog issued it. */
  nodeId: string
  nodeLabel: string
  /**
   * Every schema of this connection a table may be made in.
   *
   * Where a table goes is a choice, not the accident of which schema was
   * being looked at when the menu was opened. The list is the level's own
   * groupings with the source's machinery left out, so nothing here decides
   * what a schema is.
   */
  destinations?: { value: string; label: string }[]
  /** Whether the source calls its schemas databases, as MySQL does (D229). */
  databases?: boolean
  running: boolean
  error: string
}>()

const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  run: [value: { nodeId: string; params: Record<string, unknown> }]
}>()

const confirm = useConfirm()
const connectorId = computed(() => props.connectorId)
/** Where the table is going. It starts where the menu was opened. */
const destination = ref(props.nodeId)
watch(() => props.nodeId, (id) => { destination.value = id })
const options = useTableDesignOptions(connectorId, destination)
const planTable = usePlanTable()

const draft = reactive<Draft>(emptyDraft("text"))
draft.name = "new table"
const step = ref<"definition" | "review">("definition")
const section = ref<DraftSection>("columns")
const selected = ref(draft.columns[0]?.id ?? "")
const plan = ref<TablePlan | null>(null)
const lastValidPlan = ref<TablePlan | null>(null)
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
    label: column.name || t("table_design.unnamed"),
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
const engine = computed(() => {
  const engines = options.data.value?.engines ?? []
  return engines.find((option) => option.code === draft.engine) ?? engines[0] ?? null
})
registerDesign(designId, {
  draft,
  options: computed(() => options.data.value ?? null),
  abilities: computed(() => options.data.value?.abilities ?? {}),
  engine,
  sorted: computed(() => engine.value?.sorted !== false),
  columnChoices,
  typeChoices,
  types,
  functions: computed(() => options.data.value?.functions ?? []),
  databases: computed(() => props.databases === true),
})

// The first column takes a type this server actually publishes. Seeded rather
// than hard-coded: which types exist is the source's answer, and the draft is
// built before that answer arrives — or after it, from the cache, when the
// window is opened again, which is why the watch runs at once.
watch(types, (published) => {
  const [first] = published
  if (first === undefined) return
  for (const column of draft.columns) {
    if (!published.some((option) => option.code === column.typeCode)) {
      column.typeCode = first.code
    }
  }
}, { immediate: true })

const problems = computed(() => plan.value?.problems ?? [])
const statements = computed(() => plan.value?.statements ?? [])
const previousPreview = computed(
  () => problems.value.length > 0 && statements.value.length === 0 && lastValidPlan.value !== null
)
const previewStatements = computed(() =>
  previousPreview.value ? lastValidPlan.value?.statements ?? [] : statements.value
)
const script = computed(
  () =>
    previewStatements.value.map((statement) => statement.sql).join(";\n\n") +
    (previewStatements.value.length ? ";" : "")
)
/** The part of the plan the selected object is responsible for. */
const selectedSql = computed(() => {
  const own = previewStatements.value.filter((statement) => statement.object_id === selected.value)
  const [first] = own.length > 0 ? own : previewStatements.value
  return first ? first.sql + ";" : ""
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
  if (!worthPlanning(draft)) return t("table_design.designer.name_first")
  if (planTable.isPending.value || stale.value) return t("table_design.designer.working_out")
  if (problems.value.length > 0) {
    return t("table_design.designer.problems", { n: problems.value.length }, problems.value.length)
  }
  return t("table_design.designer.preview_only")
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
      nodeId: destination.value,
      definition: definition.value,
      revision,
    })
    // A late answer about an older draft is dropped rather than shown.
    if (answer.revision === asked) {
      plan.value = answer
      if ((answer.problems ?? []).length === 0 && (answer.statements ?? []).length > 0) lastValidPlan.value = answer
    }
  } catch (cause) {
    if (revision === asked) {
      plan.value = null
      trouble.value = messageOf(cause, t("table_design.designer.plan_failed"))
    }
  }
}

// The preview is wanted from the moment the window opens, not after the first
// edit: ask as soon as the destination's options — and with them the types the
// definition is written in — have answered.
watch(
  () => options.data.value,
  (answered) => {
    if (answered) schedulePlan()
  },
  { immediate: true }
)

// The schema is part of every statement the plan composes, so moving the
// table asks again just as editing it does.
watch(destination, () => {
  touched.value = true
  if (step.value === "review") step.value = "definition"
  schedulePlan()
})

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
    const foreign = newForeignKey(destination.value)
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
        title: t("table_design.designer.remove_title", { name }),
        message: t("table_design.designer.remove_message", { list: [...new Set(affected)].join(", ") }),
        confirmLabel: t("table_design.designer.remove"),
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
    if (draft.hypertable?.reorderIndexId === objectId) draft.hypertable.reorderIndexId = ""
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
    nodeId: destination.value,
    params: { definition: definition.value, fingerprint: held.fingerprint },
  })
}

/** A draft nobody has touched closes without a question. */
async function mayClose(): Promise<boolean> {
  if (!touched.value || props.running) return true
  return confirm({
    title: t("table_design.designer.discard_title"),
    message: t("table_design.designer.discard_message"),
    confirmLabel: t("table_design.designer.discard"),
    danger: true,
  })
}

const openedIn = computed(
  () => options.data.value?.schema_label || props.nodeLabel
)

/**
 * Where the table may go, the place the menu was opened in always among them.
 *
 * A level that lists no groupings still has to offer the one destination it
 * has, or the field would name nowhere at all.
 */
const places = computed(() => {
  const offered = props.destinations ?? []
  if (props.nodeId === "") return offered
  if (offered.some((place) => place.value === props.nodeId)) return offered
  return [{ value: props.nodeId, label: openedIn.value }, ...offered]
})

const schemaLabel = computed(
  () =>
    places.value.find((place) => place.value === destination.value)?.label ??
    openedIn.value
)
/** The dictionary's spelling of a section, which cannot hold a hyphen. */
const SECTION_KEYS = {
  columns: "columns",
  indexes: "indexes",
  "foreign-keys": "foreign_keys",
  constraints: "constraints",
  options: "options",
} as const satisfies Record<DraftSection, string>
const sectionKey = computed(() => SECTION_KEYS[section.value])
/** The section's own objects; Options holds none, and shows no add or remove. */
const objectKey = computed(() => {
  const key = sectionKey.value
  return key === "options" ? null : key
})
const editorTitle = computed(() =>
  section.value === "columns"
    ? draft.columns.find((column) => column.id === selected.value)?.name ||
      t("table_design.designer.headings.columns")
    : t(`table_design.designer.headings.${sectionKey.value}`)
)
const summary = computed(() =>
  [
    t("catalog.count.column", { n: draft.columns.length }, draft.columns.length),
    t("table_design.count.index", { n: draft.indexes.length }, draft.indexes.length),
    t("table_design.count.foreign_key", { n: draft.foreignKeys.length }, draft.foreignKeys.length),
  ].join(" · ")
)
const columnPosition = computed(() =>
  draft.columns.findIndex((column) => column.id === selected.value)
)
function moveColumn(by: number): void {
  const at = columnPosition.value
  const to = at + by
  if (at < 0 || to < 0 || to >= draft.columns.length) return
  const [column] = draft.columns.splice(at, 1)
  if (column) draft.columns.splice(to, 0, column)
}
</script>

<template>
  <WindowDialog
    :model-value="modelValue"
    size="xl"
    sizing="stable"
    :title="t('table_design.designer.title')"
    :before-close="mayClose"
    data-testid="table-designer"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="designer">
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
        v-else-if="options.data.value?.supported === false"
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
      <template v-else-if="step === 'definition'">
        <AppForm
          layout="grid"
          class="designer__identity"
          data-testid="design-identity"
        >
          <AppSelect
            v-model="destination"
            :options="places"
            :label="props.databases ? t('table_design.designer.database') : t('table_design.designer.schema')"
            data-testid="table-schema"
          />
          <AppInput
            v-model="draft.name"
            :label="t('table_design.designer.table_name')"
            data-testid="table-name"
          />
          <AppInput
            v-if="options.data.value?.abilities?.comments"
            v-model="draft.comment"
            class="designer__comment"
            :label="t('table_design.comment')"
          />
        </AppForm>
        <div
          class="designer__body"
          data-testid="design-body"
        >
          <DesignNavigation
            :design-id="designId"
            :section="section"
            :selected="selected"
            :problems="problems"
            @select="select"
          />
          <main
            class="designer__editor"
            data-testid="design-inspector"
          >
            <div class="designer__toolbar">
              <strong>{{ editorTitle }}</strong>
              <AppButton
                v-if="objectKey !== null"
                variant="quiet"
                :icon="appIcons.add"
                :label="t(`table_design.designer.add.${objectKey}`)"
                :aria-label="t(`table_design.designer.add_aria.${objectKey}`)"
                :data-testid="`add-${section}`"
                @click="add(section)"
              />
            </div>
            <AppForm layout="grid">
              <ColumnInspector
                v-if="section === 'columns'"
                :key="`column:${selected}`"
                :design-id="designId"
                :column-id="selected"
              />
              <IndexInspector
                v-else-if="section === 'indexes'"
                :key="`index:${selected}`"
                :design-id="designId"
                :index-id="selected"
              />
              <ForeignKeyInspector
                v-else-if="section === 'foreign-keys'"
                :key="`foreign-key:${selected}`"
                :design-id="designId"
                :foreign-key-id="selected"
                :connector-id="connectorId"
              />
              <ConstraintInspector
                v-else-if="section === 'constraints'"
                :design-id="designId"
                @remove="remove('constraints', $event)"
              />
              <HypertableInspector
                v-else-if="selected === 'hypertable'"
                :design-id="designId"
              />
              <TableOptionsInspector
                v-else
                :design-id="designId"
              />
              <div
                v-if="section !== 'options' && section !== 'constraints' && selected"
                class="designer__object-actions"
                :class="{ 'designer__object-actions--column': section === 'columns' }"
              >
                <template v-if="section === 'columns'">
                  <AppButton
                    variant="quiet"
                    :label="t('table_design.designer.move_up')"
                    :icon="appIcons.arrowUpward"
                    :disable="columnPosition <= 0"
                    @click="moveColumn(-1)"
                  />
                  <AppButton
                    variant="quiet"
                    :label="t('table_design.designer.move_down')"
                    :icon="appIcons.arrowDownward"
                    :disable="columnPosition >= draft.columns.length - 1"
                    @click="moveColumn(1)"
                  />
                </template>
                <AppButton
                  variant="quiet"
                  :icon="appIcons.deleteOutline"
                  :label="objectKey === null ? '' : t(`table_design.designer.remove_object.${objectKey}`)"
                  :disable="section === 'columns' && draft.columns.length === 1"
                  data-testid="remove-object"
                  @click="remove(section, selected)"
                />
              </div>
            </AppForm>
          </main>
          <aside
            class="designer__sql"
            :aria-label="t('table_design.designer.sql_preview')"
            data-testid="design-sql"
            :aria-busy="stale"
          >
            <div class="designer__sql-head">
              <span>{{ t('table_design.designer.sql_preview') }}</span><span>{{ stale && worthPlanning(draft) ? t('table_design.designer.updating') : previousPreview ? t('table_design.designer.previous_valid') : t('table_design.designer.live') }}</span>
            </div>
            <div
              v-if="problems.length"
              class="designer__problems"
              data-testid="design-problems"
              role="alert"
            >
              <ul>
                <li
                  v-for="(problem, at) in problems"
                  :key="at"
                >
                  {{ problem.message }}
                </li>
              </ul>
            </div>
            <div :class="{ 'designer__sql--stale': stale }">
              <DesignSql :sql="selectedSql" />
              <details
                v-if="previewStatements.length"
                class="dp-disclosure"
              >
                <summary>{{ t('table_design.designer.full_script') }}</summary>
                <DesignSql :sql="script" />
              </details>
            </div>
          </aside>
        </div>
      </template>
      <section
        v-else
        class="designer__review"
        data-testid="design-review"
        :aria-label="t('table_design.designer.review_aria')"
      >
        <div class="designer__toolbar">
          <strong>{{ t('table_design.designer.review_title', { schema: schemaLabel, name: draft.name }) }}</strong>
          <AppButton
            variant="quiet"
            :label="t('table_design.designer.back')"
            data-testid="design-back"
            @click="step = 'definition'"
          />
        </div>
        <DesignSql :sql="script" />
      </section>
    </div>
    <template #actions>
      <span
        v-if="step === 'definition'"
        class="designer__status"
        aria-live="polite"
        data-testid="design-status"
      >{{ summary }} · {{ status }}</span>
      <span
        v-else
        class="designer__status"
      >{{ t('table_design.designer.nothing_created') }}</span>
      <AppButton
        v-if="step === 'definition'"
        :label="t('table_design.designer.review_sql')"
        :icon-right="appIcons.arrowForward"
        :disable="!ready"
        data-testid="design-review-sql"
        @click="step = 'review'"
      />
      <AppButton
        v-else
        :label="t('table_design.designer.title')"
        :loading="running"
        :disable="!ready"
        data-testid="design-create"
        @click="create"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.designer {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  container: table-designer / inline-size;
}
/* A floating window follows the size of what it holds, and what this one holds
   until the destination has answered is a spinner: fitted to that, it shrank to
   an empty strip and sprang back to an editor the moment the answer arrived.
   The wait keeps roughly the room the editor takes, so the window is opened
   once at the size it stays. */
.designer__waiting {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 460px;
  padding: var(--dp-space-5);
}
.designer__identity {
  display: grid;
  grid-template-columns: 150px minmax(150px, 1fr) minmax(180px, 1.3fr);
  gap: var(--dp-space-3);
  padding: var(--dp-space-3);
  border-bottom: 1px solid var(--dp-border);
}
/* The body itself does not scroll: the navigation and the SQL preview keep
   the full height of the window while only the editor between them scrolls. */
.designer__body {
  flex: 1;
  display: grid;
  grid-template-columns: 208px minmax(0, 1fr) minmax(250px, 0.78fr);
  grid-template-rows: minmax(0, 1fr);
  min-height: 0;
  overflow: hidden;
}
.designer__editor {
  padding: var(--dp-space-3);
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
}
.designer__toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--dp-space-2);
  min-height: 31px;
  margin-bottom: var(--dp-space-2);
}
.designer__toolbar strong {
  overflow-wrap: anywhere;
}
.designer__object-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--dp-space-2);
  padding-top: var(--dp-space-2);
  margin-top: var(--dp-space-3);
  border-top: 1px solid var(--dp-border);
}
.designer__object-actions--column > :last-child {
  margin-inline-start: auto;
}
.designer__sql {
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  background: var(--dp-chrome-raised);
  border-inline-start: 1px solid var(--dp-border);
}
.designer__sql-head {
  display: flex;
  justify-content: space-between;
  gap: var(--dp-space-2);
  padding: var(--dp-space-2) var(--dp-space-3);
  border-bottom: 1px solid var(--dp-border);
  color: var(--dp-text-muted);
}
.designer__sql--stale {
  opacity: var(--dp-opacity-dim);
}
.designer__sql summary {
  padding: var(--dp-space-2) var(--dp-space-3);
}
.designer__problems {
  padding: var(--dp-space-2) var(--dp-space-3);
  border-bottom: 1px solid var(--dp-border);
  color: var(--dp-content-error);
}
.designer__problems ul {
  margin: 0;
  padding-inline-start: var(--dp-space-4);
}
.designer__status {
  margin-inline-end: auto;
  color: var(--dp-text-muted);
}
.designer__review {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: var(--dp-space-3);
}
@container table-designer (max-width: 850px) {
  .designer__identity {
    grid-template-columns: minmax(0, 1fr);
  }
  /* Two rows again: the preview moves under the editor, and the body scrolls
     as one piece like it does at every width outside the three-column one. */
  .designer__body {
    grid-template-columns: 160px minmax(0, 1fr);
    grid-template-rows: max-content max-content;
    overflow: auto;
  }
  .designer__editor,
  .designer__sql {
    overflow-y: visible;
  }
  .designer__sql {
    grid-column: 1 / -1;
    border-inline-start: 0;
    border-top: 1px solid var(--dp-border);
  }
}
@container table-designer (max-width: 560px) {
  .designer__body {
    display: block;
  }
}
</style>
