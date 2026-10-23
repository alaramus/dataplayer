"""The emails in Spanish: their subjects and the sentences of their templates."""

MESSAGES: dict[str, str] = {
    "{project} - Test email": "{project} — Correo de prueba",
    "{project} - Password recovery for user {email}": "{project} — Recuperación de contraseña para el usuario {email}",
    "{project} - New account for user {name}": "{project} — Nueva cuenta para el usuario {name}",
    "{project} - New account": "{project} — Nueva cuenta",
    "{project} - Password recovery": "{project} — Recuperación de contraseña",
    "Your {project} account is ready": "Tu cuenta de {project} está lista",
    "Welcome to {project}!": "¡Te damos la bienvenida a {project}!",
    "Hi,": "Hola:",
    "Hi {name},": "Hola, {name}:",
    "Your account has been successfully created and is ready to use. These are your credentials:": (
        "Tu cuenta se ha creado correctamente y ya puedes usarla. Estos son tus datos de acceso:"
    ),
    "Username": "Nombre de usuario",
    "Password": "Contraseña",
    "Get started by signing in to your dashboard:": "Empieza iniciando sesión en tu panel:",
    "Go to Dashboard": "Ir al panel",
    "Or copy and paste this link into your browser:": "O copia y pega este enlace en tu navegador:",
    "For security reasons, change your password after your first sign in.": (
        "Por seguridad, cambia tu contraseña después de iniciar sesión por primera vez."
    ),
    "All rights reserved.": "Todos los derechos reservados.",
    "Reset your {project} password": "Restablece tu contraseña de {project}",
    "Reset your password": "Restablece tu contraseña",
    "We've received a request to reset the password for your {project} account. Choose a new one by clicking the button below:": (
        "Hemos recibido una solicitud para restablecer la contraseña de tu cuenta de {project}. Elige una nueva haciendo clic en el botón de abajo:"
    ),
    "Reset password": "Restablecer contraseña",
    "This link will expire in {hours} hours.": "Este enlace caducará en {hours} horas.",
    "If you didn't request a password recovery, you can safely ignore this email.": (
        "Si no has solicitado la recuperación de contraseña, puedes ignorar este correo sin problema."
    ),
    "{project} email delivery is working": "El envío de correos de {project} funciona",
    "Test email": "Correo de prueba",
    "This is a test email from {project}. If you're reading it, email delivery is configured correctly.": (
        "Este es un correo de prueba de {project}. Si lo estás leyendo, el envío de correos está configurado correctamente."
    ),
    "Sent to": "Enviado a",
    "If you weren't expecting this email, you can safely ignore it.": (
        "Si no esperabas este correo, puedes ignorarlo sin problema."
    ),
}
