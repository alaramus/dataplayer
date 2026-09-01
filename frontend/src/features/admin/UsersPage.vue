<script setup lang="ts">
import { computed, ref } from "vue"
import { useRouter } from "vue-router"

import type { UserPublic } from "@/client"
import { useCreateUser, useDeleteUser, useUpdateUser, useUsers } from "@/features/admin/api"
import {
  emptyForm,
  formOf,
  toCreate,
  toUpdate,
  undeletableReason,
  validate,
} from "@/features/admin/users"
import type { UserForm } from "@/features/admin/users"
import { useCurrentUser } from "@/features/auth/api"
import { messageOf } from "@/shared/api/errors"
import {
  AppBadge,
  AppButton,
  AppCheckbox,
  AppEmptyState,
  AppIconButton,
  AppInput,
  AppLayout,
  AppPageHeader,
  AppTable,
  useConfirm,
  useToast,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"
import type { TableColumns } from "@/shared/ui"

/**
 * The accounts of this installation.
 *
 * An administrator's screen and nothing more: it creates people, switches them
 * off and removes them. What any of them may reach is decided on the
 * connection itself, by whoever owns it — see D33 and D34.
 *
 * A page rather than a floating window: it is not work done beside a table,
 * and it is opened from the header rather than from anything on the workspace.
 */
const router = useRouter()
const toast = useToast()
const confirm = useConfirm()

const me = useCurrentUser()
const users = useUsers()
const createUser = useCreateUser()
const updateUser = useUpdateUser()
const removeUser = useDeleteUser()

const isAdmin = computed(() => me.data.value?.is_superuser === true)
const myId = computed(() => me.data.value?.id ?? null)

const editing = ref<UserPublic | null>(null)
const dialogOpen = ref(false)
const form = ref<UserForm>(emptyForm())
const errors = ref<Record<string, string>>({})

const isNew = computed(() => editing.value === null)
const saving = computed(() => createUser.isPending.value || updateUser.isPending.value)

const columns: TableColumns = [
  { name: "email", label: "Email", field: "email", align: "left", sortable: true },
  { name: "full_name", label: "Name", field: "full_name", align: "left", sortable: true },
  { name: "role", label: "Role", field: "id", align: "left" },
  { name: "state", label: "State", field: "id", align: "left" },
  { name: "actions", label: "", field: "id", align: "right" },
]

const rows = computed(() => users.data.value?.data ?? [])

function openNew() {
  editing.value = null
  form.value = emptyForm()
  errors.value = {}
  dialogOpen.value = true
}

function openEdit(user: UserPublic) {
  editing.value = user
  form.value = formOf(user)
  errors.value = {}
  dialogOpen.value = true
}

async function save() {
  errors.value = validate(form.value, isNew.value)
  if (Object.keys(errors.value).length > 0) return

  try {
    if (editing.value === null) {
      await createUser.mutateAsync(toCreate(form.value))
      toast.success("Account created")
    } else {
      await updateUser.mutateAsync({
        userId: editing.value.id,
        body: toUpdate(form.value),
      })
      toast.success("Account updated")
    }
    dialogOpen.value = false
  } catch (error) {
    toast.error(messageOf(error, "That account could not be saved"))
  }
}

async function remove(user: UserPublic) {
  const ok = await confirm({
    title: "Delete account",
    message: `${user.email} and everything they own — their connections and their files — will be removed. This cannot be undone.`,
    confirmLabel: "Delete",
    danger: true,
  })
  if (!ok) return
  try {
    await removeUser.mutateAsync(user.id)
    toast.success("Account deleted")
  } catch (error) {
    toast.error(messageOf(error, "That account could not be deleted"))
  }
}
</script>

<template>
  <AppLayout>
    <AppPageHeader title="Users">
      <template #actions>
        <AppButton
          variant="quiet"
          label="Back to workspace"
          data-testid="back-to-workspace"
          @click="router.push({ name: 'workspace' })"
        />
        <AppButton
          v-if="isAdmin"
          label="New user"
          data-testid="new-user"
          @click="openNew"
        />
      </template>
    </AppPageHeader>

    <!-- The server answers 403 to everybody else; this says so before the
         screen shows an empty table and leaves the reason to be guessed. -->
    <AppEmptyState
      v-if="me.isFetched.value && !isAdmin"
      text="Only an administrator manages accounts"
    />

    <AppTable
      v-else
      :rows="rows"
      :columns="columns"
      row-key="id"
      :loading="users.isLoading.value"
      empty-text="No accounts yet"
      data-testid="users-table"
    >
      <template #body-cell-role="cellProps">
        <q-td :props="cellProps">
          <AppBadge
            v-if="cellProps.row.is_superuser"
            label="Administrator"
            tone="info"
          />
          <span v-else>User</span>
        </q-td>
      </template>

      <template #body-cell-state="cellProps">
        <q-td :props="cellProps">
          <AppBadge
            :label="cellProps.row.is_active ? 'Active' : 'Switched off'"
            :tone="cellProps.row.is_active ? 'success' : 'warning'"
          />
        </q-td>
      </template>

      <template #body-cell-actions="cellProps">
        <q-td :props="cellProps">
          <AppIconButton
            icon="edit"
            tooltip="Edit this account"
            :data-testid="`edit-user-${cellProps.row.email}`"
            @click="openEdit(cellProps.row)"
          />
          <AppIconButton
            icon="delete"
            variant="danger-quiet"
            :tooltip="
              undeletableReason(cellProps.row, myId) || 'Delete this account and all it owns'
            "
            :disable="undeletableReason(cellProps.row, myId) !== ''"
            :data-testid="`delete-user-${cellProps.row.email}`"
            @click="remove(cellProps.row)"
          />
        </q-td>
      </template>
    </AppTable>

    <WindowDialog
      v-model="dialogOpen"
      :title="isNew ? 'New user' : 'Edit user'"
      :subtitle="isNew ? undefined : editing?.email"
      data-testid="user-dialog"
    >
      <div class="user-form">
        <AppInput
          v-model="form.email"
          label="Email"
          data-testid="user-email"
          :error="errors.email"
        />
        <AppInput
          v-model="form.fullName"
          label="Name"
          data-testid="user-name"
        />
        <AppInput
          v-model="form.password"
          type="password"
          :label="isNew ? 'Password' : 'New password — leave empty to keep the current one'"
          data-testid="user-password"
          :error="errors.password"
        />
        <AppCheckbox
          v-model="form.isActive"
          label="Can sign in"
          data-testid="user-active"
        />
        <AppCheckbox
          v-model="form.isSuperuser"
          label="Administrator: manages accounts, not other people's data"
          data-testid="user-superuser"
        />
      </div>

      <template #actions>
        <AppButton
          variant="quiet"
          label="Cancel"
          data-testid="user-cancel"
          @click="dialogOpen = false"
        />
        <AppButton
          label="Save"
          data-testid="user-save"
          :loading="saving"
          @click="save"
        />
      </template>
    </WindowDialog>
  </AppLayout>
</template>

<style scoped>
.user-form {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-2);
  padding: 0 var(--dp-space-3) var(--dp-space-2);
}
</style>
