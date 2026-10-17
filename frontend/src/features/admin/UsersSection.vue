<script setup lang="ts">
import { appIcons } from "@/shared/ui"
import { computed, ref } from "vue"

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
import { messageOf } from "@/shared/api/errors"
import { useCurrentUser } from "@/shared/auth/currentUser"
import { t } from "@/shared/i18n"
import {
  AppBadge,
  AppButton,
  AppCheckbox,
  AppEmptyState,
  AppForm,
  AppIconButton,
  AppInput,
  AppTable,
  useConfirm,
  useToast,
} from "@/shared/ui"
import { WindowDialog } from "@/shared/windows"
import type { TableColumns } from "@/shared/ui"

/**
 * The accounts of this installation: creating people, switching them off and
 * removing them. What any of them may reach is decided on the connection
 * itself, by whoever owns it (D33, D34).
 */
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

const columns = computed<TableColumns>(() => [
  { name: "email", label: t("admin.users.columns.email"), field: "email", align: "left", sortable: true },
  { name: "full_name", label: t("admin.users.columns.name"), field: "full_name", align: "left", sortable: true },
  { name: "role", label: t("admin.users.columns.role"), field: "id", align: "left" },
  { name: "state", label: t("admin.users.columns.state"), field: "id", align: "left" },
  { name: "actions", label: "", field: "id", align: "right" },
])

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
      toast.success(t("admin.users.created"))
    } else {
      await updateUser.mutateAsync({
        userId: editing.value.id,
        body: toUpdate(form.value),
      })
      toast.success(t("admin.users.updated"))
    }
    dialogOpen.value = false
  } catch (error) {
    toast.error(messageOf(error, t("admin.users.save_failed")))
  }
}

async function remove(user: UserPublic) {
  const ok = await confirm({
    title: t("admin.users.delete_title"),
    message: t("admin.users.delete_message", { email: user.email }),
    confirmLabel: t("admin.users.delete_confirm"),
    danger: true,
  })
  if (!ok) return
  try {
    await removeUser.mutateAsync(user.id)
    toast.success(t("admin.users.deleted"))
  } catch (error) {
    toast.error(messageOf(error, t("admin.users.delete_failed")))
  }
}
</script>

<template>
  <div class="users-section">
    <div class="users-section__head">
      <AppButton
        v-if="isAdmin"
        :label="t('admin.users.new_user')"
        data-testid="new-user"
        @click="openNew"
      />
    </div>

    <!-- The server answers 403 to everybody else; this says so before the
         screen shows an empty table and leaves the reason to be guessed. -->
    <AppEmptyState
      v-if="me.isFetched.value && !isAdmin"
      :text="t('admin.users.only_admin')"
    />

    <AppTable
      v-else
      :rows="rows"
      :columns="columns"
      row-key="id"
      :loading="users.isLoading.value"
      :empty-text="t('admin.users.empty')"
      data-testid="users-table"
    >
      <template #body-cell-role="cellProps">
        <q-td :props="cellProps">
          <AppBadge
            v-if="cellProps.row.is_superuser"
            :label="t('admin.users.administrator')"
            tone="info"
          />
          <span v-else>{{ t('admin.users.user') }}</span>
        </q-td>
      </template>

      <template #body-cell-state="cellProps">
        <q-td :props="cellProps">
          <AppBadge
            :label="cellProps.row.is_active ? t('admin.users.active') : t('admin.users.switched_off')"
            :tone="cellProps.row.is_active ? 'success' : 'warning'"
          />
        </q-td>
      </template>

      <template #body-cell-actions="cellProps">
        <q-td :props="cellProps">
          <AppIconButton
            :icon="appIcons.edit"
            :tooltip="t('admin.users.edit')"
            :data-testid="`edit-user-${cellProps.row.email}`"
            @click="openEdit(cellProps.row)"
          />
          <AppIconButton
            :icon="appIcons.delete"
            variant="danger-quiet"
            :tooltip="
              undeletableReason(cellProps.row, myId) || t('admin.users.delete')
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
      :title="isNew ? t('admin.users.new_user') : t('admin.users.edit_title', { email: editing?.email ?? '' })"
      size="medium-form"
      sizing="stable"
      data-testid="user-dialog"
    >
      <AppForm layout="section">
        <AppInput
          v-model="form.email"
          :label="t('admin.users.email')"
          type="email"
          autocomplete="off"
          persistent-label
          data-testid="user-email"
          :error="errors.email"
        />
        <AppInput
          v-model="form.fullName"
          :label="t('admin.users.name')"
          autocomplete="off"
          persistent-label
          data-testid="user-name"
        />
        <AppInput
          v-model="form.password"
          type="password"
          autocomplete="new-password"
          persistent-label
          :label="isNew ? t('admin.users.password') : t('admin.users.new_password')"
          :hint="isNew ? undefined : t('admin.users.keep_password')"
          data-testid="user-password"
          :error="errors.password"
        />
        <AppCheckbox
          v-model="form.isActive"
          :label="t('admin.users.can_sign_in')"
          data-testid="user-active"
        />
        <AppCheckbox
          v-model="form.isSuperuser"
          :label="t('admin.users.superuser')"
          data-testid="user-superuser"
        />
      </AppForm>

      <template #actions>
        <AppButton
          variant="quiet"
          :label="t('catalog.common.cancel')"
          data-testid="user-cancel"
          @click="dialogOpen = false"
        />
        <AppButton
          :label="t('catalog.common.save')"
          data-testid="user-save"
          :loading="saving"
          @click="save"
        />
      </template>
    </WindowDialog>
  </div>
</template>

<style scoped>
.users-section {
  display: flex;
  flex-direction: column;
  gap: var(--dp-space-3);
  min-width: 0;
}

/* The one action this section has, kept off the table it acts on. */
.users-section__head {
  display: flex;
  justify-content: flex-end;
}

</style>
