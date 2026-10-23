"""Les e-mails en français : leurs objets et les phrases de leurs modèles."""

MESSAGES: dict[str, str] = {
    "{project} - Test email": "{project} — E-mail de test",
    "{project} - Password recovery for user {email}": "{project} — Réinitialisation du mot de passe pour {email}",
    "{project} - New account for user {name}": "{project} — Nouveau compte pour {name}",
    "{project} - New account": "{project} — Nouveau compte",
    "{project} - Password recovery": "{project} — Réinitialisation du mot de passe",
    "Your {project} account is ready": "Votre compte {project} est prêt",
    "Welcome to {project}!": "Bienvenue sur {project} !",
    "Hi,": "Bonjour,",
    "Hi {name},": "Bonjour {name},",
    "Your account has been successfully created and is ready to use. These are your credentials:": (
        "Votre compte a été créé avec succès et est prêt à l'emploi. Voici vos identifiants :"
    ),
    "Username": "Nom d'utilisateur",
    "Password": "Mot de passe",
    "Get started by signing in to your dashboard:": "Connectez-vous à votre tableau de bord pour commencer :",
    "Go to Dashboard": "Aller au tableau de bord",
    "Or copy and paste this link into your browser:": "Ou copiez-collez ce lien dans votre navigateur :",
    "For security reasons, change your password after your first sign in.": (
        "Pour des raisons de sécurité, changez votre mot de passe après votre première connexion."
    ),
    "All rights reserved.": "Tous droits réservés.",
    "Reset your {project} password": "Réinitialisez votre mot de passe {project}",
    "Reset your password": "Réinitialisez votre mot de passe",
    "We've received a request to reset the password for your {project} account. Choose a new one by clicking the button below:": (
        "Nous avons reçu une demande de réinitialisation du mot de passe de votre compte {project}. "
        "Choisissez-en un nouveau en cliquant sur le bouton ci-dessous :"
    ),
    "Reset password": "Réinitialiser le mot de passe",
    "This link will expire in {hours} hours.": "Ce lien expirera dans {hours} heures.",
    "If you didn't request a password recovery, you can safely ignore this email.": (
        "Si vous n'avez pas demandé de réinitialisation du mot de passe, vous pouvez ignorer cet e-mail."
    ),
    "{project} email delivery is working": "L'envoi des e-mails de {project} fonctionne",
    "Test email": "E-mail de test",
    "This is a test email from {project}. If you're reading it, email delivery is configured correctly.": (
        "Ceci est un e-mail de test de {project}. Si vous le lisez, l'envoi des e-mails est correctement configuré."
    ),
    "Sent to": "Envoyé à",
    "If you weren't expecting this email, you can safely ignore it.": (
        "Si vous n'attendiez pas cet e-mail, vous pouvez l'ignorer."
    ),
}
