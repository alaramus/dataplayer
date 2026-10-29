"""رسائل البريد الإلكتروني بالعربية: عناوينها وجمل قوالبها."""

MESSAGES: dict[str, str] = {
    "{project} - Test email": "{project} - بريد اختبار",
    "{project} - Password recovery for user {email}": "{project} - استعادة كلمة مرور المستخدم {email}",
    "{project} - New account for user {name}": "{project} - حساب جديد للمستخدم {name}",
    "{project} - New account": "{project} - حساب جديد",
    "{project} - Password recovery": "{project} - استعادة كلمة المرور",
    "Your {project} account is ready": "حسابك في {project} جاهز",
    "Welcome to {project}!": "مرحبًا بك في {project}!",
    "Hi,": "مرحبًا،",
    "Hi {name},": "مرحبًا، {name}،",
    "Your account has been successfully created and is ready to use. These are your credentials:": (
        "أُنشئ حسابك بنجاح وأصبح جاهزًا للاستخدام. هذه بيانات الدخول:"
    ),
    "Username": "اسم المستخدم",
    "Password": "كلمة المرور",
    "Get started by signing in to your dashboard:": "ابدأ بتسجيل الدخول إلى لوحة التحكم:",
    "Go to Dashboard": "الانتقال إلى لوحة التحكم",
    "Or copy and paste this link into your browser:": "أو انسخ هذا الرابط وألصقه في متصفحك:",
    "For security reasons, change your password after your first sign in.": (
        "لأسباب أمنية، غيّر كلمة مرورك بعد أول تسجيل دخول."
    ),
    "All rights reserved.": "جميع الحقوق محفوظة.",
    "Reset your {project} password": "أعد تعيين كلمة مرورك في {project}",
    "Reset your password": "أعد تعيين كلمة مرورك",
    "We've received a request to reset the password for your {project} account. Choose a new one by clicking the button below:": (
        "تلقّينا طلبًا لاستعادة كلمة المرور لحسابك في {project}. اختر كلمة جديدة بالنقر على الزر أدناه:"
    ),
    "Reset password": "إعادة تعيين كلمة المرور",
    "This link will expire in {hours} hours.": "تنتهي صلاحية هذا الرابط خلال {hours} ساعة.",
    "If you didn't request a password recovery, you can safely ignore this email.": (
        "إذا لم تطلب استعادة كلمة المرور، يمكنك تجاهل هذا البريد دون قلق."
    ),
    "{project} email delivery is working": "إرسال البريد من {project} يعمل",
    "Test email": "بريد اختبار",
    "This is a test email from {project}. If you're reading it, email delivery is configured correctly.": (
        "هذا بريد اختبار من {project}. إذا كنت تقرأه، فإرسال البريد مُعدّ بشكل صحيح."
    ),
    "Sent to": "أُرسل إلى",
    "If you weren't expecting this email, you can safely ignore it.": (
        "إذا لم تكن تتوقع هذا البريد، يمكنك تجاهله دون قلق."
    ),
}
