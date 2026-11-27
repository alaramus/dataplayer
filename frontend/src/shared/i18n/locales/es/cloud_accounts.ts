import type { Messages } from "../en"

/** Cuentas en la nube con las que inician sesión las conexiones (features/cloudAccounts). */
export const cloud_accounts: Messages["cloud_accounts"] = {
  section: {
    title: "Cuentas en la nube",
    hint: "Cuentas de las que sus conexiones obtienen contraseñas y tokens: Amazon Web Services, Google Cloud, Microsoft Azure y HashiCorp Vault. Se emite un token para cada nueva conexión y nunca se guarda. Los secretos escritos aquí se guardan cifrados y no se vuelven a mostrar.",
    form_hint: "Cuentas de las que sus conexiones obtienen contraseñas y tokens; una sirve para cualquier conexión. Sus secretos se guardan cifrados y no se vuelven a mostrar.",
    new_account: "Nueva cuenta",
    empty: "Aún no hay cuentas en la nube",
    unused: "Ninguna conexión la usa",
    used_by: "La usan: {names}",
    ambient: "Identidad de este servidor",
    test: "Probar la cuenta",
    test_failed: "No se pudo probar la cuenta",
    edit: "Cambiar la cuenta",
    delete_title: "¿Eliminar esta cuenta?",
    delete_message: "{name} y sus secretos desaparecerán de este servidor. Las credenciales siguen en la nube.",
    delete: "Eliminar",
    delete_failed: "No se pudo eliminar la cuenta",
    delete_used: "Primero apunte sus conexiones a otra cuenta",
    delete_account: "Eliminar esta cuenta",
  },
  dialog: {
    title_new: "Nueva cuenta en la nube",
    title_edit: "Cambiar la cuenta en la nube",
    subtitle: "Los secretos se guardan cifrados y no se vuelven a mostrar",
    name: "Nombre",
    kind: "Nube",
    make: "Crear",
    save: "Guardar",
    made: "Cuenta creada",
    saved: "Cuenta guardada",
    save_failed: "No se pudo guardar la cuenta",
  },
}
