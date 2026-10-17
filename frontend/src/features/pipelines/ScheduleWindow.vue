<script setup lang="ts">
import { computed, ref } from "vue"

import type { ScheduleSettings } from "@/client"
import { messageOf } from "@/shared/api/errors"
import { t } from "@/shared/i18n"
import {
  AppBanner,
  AppButton,
  AppCheckbox,
  AppForm,
  AppFormControl,
  AppIconButton,
  AppInput,
  AppNumberInput,
  AppRadioGroup,
  AppSelect,
  AppToggle,
  appIcons,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"

import { useSaveSchedule } from "./api"
import { browserZone, dayNames, firstSettings, intervalParts, MAX_TIMES, minutesOf } from "./schedule"
import type { IntervalUnit } from "./schedule"

/**
 * When a pipeline runs by itself (D179): every so long, or at times of the
 * day on chosen days, in this browser's clock. Kept as a whole on Save.
 */
const props = defineProps<{
  pipelineId: string
  pipelineName: string
  settings: ScheduleSettings | null | undefined
}>()

const emit = defineEmits<{ close: [] }>()

const saving = useSaveSchedule()
const zone = browserZone()
const start = props.settings ?? firstSettings(zone)
const enabled = ref(start.enabled ?? false)
const kind = ref<string>(start.kind ?? "times")
const interval = intervalParts(start.every_minutes ?? 60)
const count = ref<number | null>(interval.count)
const unit = ref<IntervalUnit>(interval.unit)
const times = ref<string[]>([...(start.times ?? ["03:00"])])
const days = ref<Set<number>>(new Set(start.days ?? []))
const failure = ref("")

// Kept while switched off, so switching back on finds them, but out of reach:
// a time set under a switched-off schedule looked like a schedule.
const off = computed(() => !enabled.value)
const kinds = computed(() => [
  {
    label: t("pipelines.schedule.window.interval"),
    value: "interval",
    description: t("pipelines.schedule.window.interval_description"),
    disable: off.value,
  },
  {
    label: t("pipelines.schedule.window.times"),
    value: "times",
    description: t("pipelines.schedule.window.times_description"),
    disable: off.value,
  },
])
const units = computed(() =>
  (["minutes", "hours", "days"] as const).map((value) => ({ label: t(`pipelines.schedule.window.units.${value}`), value }))
)
const dayLabels = computed(() => dayNames())

const chosen = computed<ScheduleSettings>(() => ({
  enabled: enabled.value,
  kind: kind.value === "interval" ? "interval" : "times",
  every_minutes: minutesOf(count.value ?? 0, unit.value),
  times: times.value.filter((time) => time !== ""),
  days: [...days.value].sort((a, b) => a - b),
  // Saved in this browser's clock, whatever it was set in before.
  time_zone: zone,
}))

function toggleDay(day: number, on: boolean) {
  const next = new Set(days.value)
  if (on) next.add(day)
  else next.delete(day)
  days.value = next
}

function setTime(index: number, value: string | number | null) {
  times.value = times.value.map((time, at) => (at === index ? String(value ?? "") : time))
}

async function save() {
  failure.value = ""
  try {
    await saving.mutateAsync({ pipelineId: props.pipelineId, settings: chosen.value })
    emit("close")
  } catch (cause) {
    failure.value = messageOf(cause, t("pipelines.schedule.window.save_failed"))
  }
}
</script>

<template>
  <WindowDialog
    :model-value="true"
    :title="t('pipelines.schedule.window.title')"
    :subtitle="t('pipelines.schedule.window.subtitle', { name: pipelineName })"
    size="form"
    sizing="stable"
    data-testid="schedule-window"
    @update:model-value="emit('close')"
  >
    <AppForm
      layout="section"
      labels="above"
    >
      <AppToggle
        v-model="enabled"
        :label="t('pipelines.schedule.window.enabled')"
        data-testid="schedule-enabled"
      />
      <AppRadioGroup
        v-model="kind"
        :options="kinds"
        :label="t('pipelines.schedule.window.when')"
        data-testid="schedule-kind"
      />
      <template v-if="kind === 'interval'">
        <AppNumberInput
          v-model="count"
          :label="t('pipelines.schedule.window.every')"
          :disable="off"
          data-testid="schedule-every"
        />
        <AppSelect
          v-model="unit"
          :options="units"
          :label="t('pipelines.schedule.window.of')"
          :disable="off"
          data-testid="schedule-unit"
        />
      </template>
      <template v-else>
        <!-- Fields of the form like any other, so "At" stands in the label
             column; inside a form control each one was set in twice. -->
        <AppInput
          v-for="(time, index) in times"
          :key="index"
          :model-value="time"
          type="time"
          :label="index === 0 ? t('pipelines.schedule.window.at') : t('pipelines.schedule.window.and_at')"
          :disable="off"
          :data-testid="`schedule-time-${index}`"
          @update:model-value="setTime(index, $event)"
        >
          <template
            v-if="times.length > 1"
            #after
          >
            <AppIconButton
              :icon="appIcons.close"
              :tooltip="t('pipelines.schedule.window.remove_time')"
              :disable="off"
              :data-testid="`schedule-time-remove-${index}`"
              @click="times = times.filter((_, at) => at !== index)"
            />
          </template>
        </AppInput>
        <AppFormControl>
          <AppButton
            variant="quiet"
            size="sm"
            :icon="appIcons.add"
            :label="t('pipelines.schedule.window.add_time')"
            :disable="off || times.length >= MAX_TIMES"
            data-testid="schedule-add-time"
            @click="times = [...times, '12:00']"
          />
        </AppFormControl>
        <AppFormControl>
          <div class="schedule-window__days">
            <AppCheckbox
              v-for="(day, index) in dayLabels"
              :key="index"
              :model-value="days.has(index)"
              class="schedule-window__day"
              :label="day"
              dense
              :disable="off"
              :data-testid="`schedule-day-${index}`"
              @update:model-value="toggleDay(index, $event)"
            />
          </div>
        </AppFormControl>
      </template>
      <AppFormControl>
        <span class="schedule-window__zone">{{ t('pipelines.schedule.window.zone', { zone }) }}</span>
      </AppFormControl>
      <AppBanner
        v-if="failure"
        tone="error"
      >
        {{ failure }}
      </AppBanner>
    </AppForm>
    <template #actions>
      <AppButton
        variant="quiet"
        :label="t('catalog.common.cancel')"
        @click="emit('close')"
      />
      <AppButton
        :label="t('catalog.common.save')"
        :loading="saving.isPending.value"
        data-testid="schedule-save"
        @click="save"
      />
    </template>
  </WindowDialog>
</template>

<style scoped>
.schedule-window__days {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--dp-space-2);
}
.schedule-window__zone {
  color: var(--dp-text-muted);
  font-size: var(--dp-font-size-sm);
}
</style>
