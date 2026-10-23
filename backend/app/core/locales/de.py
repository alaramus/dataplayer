"""Die E-Mails auf Deutsch: ihre Betreffzeilen und die Sätze ihrer Vorlagen."""

MESSAGES: dict[str, str] = {
    "{project} - Test email": "{project} – Test-E-Mail",
    "{project} - Password recovery for user {email}": "{project} – Passwort-Wiederherstellung für {email}",
    "{project} - New account for user {name}": "{project} – Neues Konto für {name}",
    "{project} - New account": "{project} – Neues Konto",
    "{project} - Password recovery": "{project} – Passwort-Wiederherstellung",
    "Your {project} account is ready": "Ihr {project}-Konto ist bereit",
    "Welcome to {project}!": "Willkommen bei {project}!",
    "Hi,": "Hallo!",
    "Hi {name},": "Hallo {name}!",
    "Your account has been successfully created and is ready to use. These are your credentials:": (
        "Ihr Konto wurde erfolgreich erstellt und kann verwendet werden. Dies sind Ihre Zugangsdaten:"
    ),
    "Username": "Benutzername",
    "Password": "Passwort",
    "Get started by signing in to your dashboard:": "Melden Sie sich an, um zu beginnen:",
    "Go to Dashboard": "Zum Dashboard",
    "Or copy and paste this link into your browser:": "Oder kopieren Sie diesen Link in Ihren Browser:",
    "For security reasons, change your password after your first sign in.": (
        "Ändern Sie aus Sicherheitsgründen Ihr Passwort nach der ersten Anmeldung."
    ),
    "All rights reserved.": "Alle Rechte vorbehalten.",
    "Reset your {project} password": "Setzen Sie Ihr {project}-Passwort zurück",
    "Reset your password": "Passwort zurücksetzen",
    "We've received a request to reset the password for your {project} account. Choose a new one by clicking the button below:": (
        "Wir haben eine Anfrage zum Zurücksetzen des Passworts für Ihr {project}-Konto erhalten. "
        "Wählen Sie ein neues, indem Sie auf die Schaltfläche unten klicken:"
    ),
    "Reset password": "Passwort zurücksetzen",
    "This link will expire in {hours} hours.": "Dieser Link läuft in {hours} Stunden ab.",
    "If you didn't request a password recovery, you can safely ignore this email.": (
        "Wenn Sie keine Passwort-Wiederherstellung angefordert haben, können Sie diese E-Mail ignorieren."
    ),
    "{project} email delivery is working": "E-Mail-Versand von {project} funktioniert",
    "Test email": "Test-E-Mail",
    "This is a test email from {project}. If you're reading it, email delivery is configured correctly.": (
        "Dies ist eine Test-E-Mail von {project}. Wenn Sie sie lesen, ist der E-Mail-Versand korrekt konfiguriert."
    ),
    "Sent to": "Gesendet an",
    "If you weren't expecting this email, you can safely ignore it.": (
        "Wenn Sie diese E-Mail nicht erwartet haben, können Sie sie ignorieren."
    ),
}
