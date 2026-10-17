"""The emails in Russian: their subjects and the sentences of their templates."""

MESSAGES: dict[str, str] = {
    "{project} - Test email": "{project} — тестовое письмо",
    "{project} - Password recovery for user {email}": "{project} — восстановление пароля для {email}",
    "{project} - New account for user {name}": "{project} — новая учётная запись {name}",
    "{project} - New account": "{project} — новая учётная запись",
    "{project} - Password recovery": "{project} — восстановление пароля",
    "Your {project} account is ready": "Ваша учётная запись в {project} готова",
    "Welcome to {project}!": "Добро пожаловать в {project}!",
    "Hi,": "Здравствуйте!",
    "Hi {name},": "Здравствуйте, {name}!",
    "Your account has been successfully created and is ready to use. These are your credentials:": (
        "Учётная запись создана, ею можно пользоваться. Данные для входа:"
    ),
    "Username": "Имя пользователя",
    "Password": "Пароль",
    "Get started by signing in to your dashboard:": "Войдите, чтобы начать работу:",
    "Go to Dashboard": "Начать работу",
    "Or copy and paste this link into your browser:": "Или скопируйте эту ссылку в адресную строку браузера:",
    "For security reasons, change your password after your first sign in.": (
        "Ради безопасности смените пароль после первого входа."
    ),
    "All rights reserved.": "Все права защищены.",
    "Reset your {project} password": "Сброс пароля в {project}",
    "Reset your password": "Сброс пароля",
    "We've received a request to reset the password for your {project} account. Choose a new one by clicking the button below:": (
        "Мы получили запрос на сброс пароля вашей учётной записи в {project}. "
        "Чтобы задать новый, нажмите кнопку ниже:"
    ),
    "Reset password": "Сбросить пароль",
    "This link will expire in {hours} hours.": "Ссылка действует {hours} ч.",
    "If you didn't request a password recovery, you can safely ignore this email.": (
        "Если вы не запрашивали сброс пароля, просто не обращайте внимания на это письмо."
    ),
    "{project} email delivery is working": "Отправка писем из {project} работает",
    "Test email": "Тестовое письмо",
    "This is a test email from {project}. If you're reading it, email delivery is configured correctly.": (
        "Это тестовое письмо от {project}. Если вы его читаете, отправка писем настроена правильно."
    ),
    "Sent to": "Кому",
    "If you weren't expecting this email, you can safely ignore it.": (
        "Если вы не ждали этого письма, просто не обращайте на него внимания."
    ),
}
