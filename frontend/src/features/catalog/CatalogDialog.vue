<script setup lang="ts">
import { AxiosError } from "axios"
import { ref, watch } from "vue"

import type { ConnectorPublic } from "@/client"
import { useCatalogLoader } from "@/features/catalog/api"
import { toTreeNodes } from "@/features/catalog/treeNodes"
import type { TreeNode } from "@/features/catalog/treeNodes"

const props = defineProps<{
  modelValue: boolean
  connector: ConnectorPublic | null
}>()

const emit = defineEmits<{ "update:modelValue": [value: boolean] }>()

const loadChildren = useCatalogLoader()

const roots = ref<TreeNode[]>([])
const expanded = ref<string[]>([])
const loading = ref(false)
const error = ref("")

function messageOf(cause: unknown): string {
  if (cause instanceof AxiosError) {
    const detail = cause.response?.data?.detail
    if (detail && typeof detail === "object" && "message" in detail) {
      return String(detail.message)
    }
  }
  return "Could not read the catalog"
}

watch(
  () => props.modelValue,
  async (open) => {
    if (!open || !props.connector) return
    roots.value = []
    expanded.value = []
    error.value = ""
    loading.value = true
    try {
      roots.value = toTreeNodes(await loadChildren(props.connector.id, null))
    } catch (cause) {
      error.value = messageOf(cause)
    } finally {
      loading.value = false
    }
  }
)

async function onLazyLoad({
  node,
  done,
  fail,
}: {
  node: TreeNode
  done: (children: TreeNode[]) => void
  fail: () => void
}) {
  if (!props.connector) return fail()
  try {
    done(toTreeNodes(await loadChildren(props.connector.id, node.id)))
  } catch (cause) {
    error.value = messageOf(cause)
    fail()
  }
}
</script>

<template>
  <q-dialog
    :model-value="modelValue"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <q-card style="width: 560px; max-width: 90vw">
      <q-card-section>
        <div class="text-h6">
          {{ connector?.name }}
        </div>
      </q-card-section>

      <q-card-section style="max-height: 60vh; overflow: auto">
        <q-banner
          v-if="error"
          dense
          class="bg-negative text-white q-mb-md"
          data-testid="catalog-error"
        >
          {{ error }}
        </q-banner>

        <div
          v-if="loading"
          class="row justify-center q-pa-md"
        >
          <q-spinner size="28px" />
        </div>

        <!-- QTree has no caption prop, so the header is rendered here: the
             default header would show the label alone and silently drop the
             data type and row estimate. -->
        <q-tree
          v-else-if="roots.length"
          v-model:expanded="expanded"
          :nodes="roots"
          node-key="id"
          data-testid="catalog-tree"
          @lazy-load="onLazyLoad"
        >
          <template #default-header="{ node }">
            <q-icon
              :name="node.icon"
              size="20px"
              class="q-mr-sm"
            />
            <span>{{ node.label }}</span>
            <span
              v-if="node.caption"
              class="text-caption text-grey q-ml-sm"
            >
              {{ node.caption }}
            </span>
          </template>
        </q-tree>

        <div
          v-else-if="!error"
          class="text-grey"
        >
          Nothing to show
        </div>
      </q-card-section>

      <q-card-actions align="right">
        <q-btn
          flat
          label="Close"
          @click="emit('update:modelValue', false)"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>
