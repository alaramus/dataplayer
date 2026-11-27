import type { Messages } from "../en"

/** الحسابات السحابية التي تسجّل بها الاتصالات الدخول (features/cloudAccounts). */
export const cloud_accounts: Messages["cloud_accounts"] = {
  section: {
    title: "الحسابات السحابية",
    hint: "حسابات تحصل منها اتصالاتك على كلمات المرور والرموز: Amazon Web Services, Google Cloud, Microsoft Azure وHashiCorp Vault. يُصدر رمز لكل اتصال جديد ولا يُخزَّن أبدًا. الأسرار المكتوبة هنا تُحفظ مشفّرة ولا تُعرض مرة أخرى.",
    form_hint: "حسابات تحصل منها اتصالاتك على كلمات المرور والرموز؛ يصلح الحساب الواحد لأي اتصال. تُحفظ أسراره مشفّرة ولا تُعرض مرة أخرى.",
    new_account: "حساب جديد",
    empty: "لا توجد حسابات سحابية بعد",
    unused: "لا يستخدمه أي اتصال",
    used_by: "يستخدمه: {names}",
    ambient: "هوية هذا الخادم",
    test: "اختبار الحساب",
    test_failed: "تعذّر اختبار الحساب",
    edit: "تغيير الحساب",
    delete_title: "حذف هذا الحساب؟",
    delete_message: "سيختفي {name} وأسراره من هذا الخادم. تبقى بيانات الاعتماد نفسها في السحابة.",
    delete: "حذف",
    delete_failed: "تعذّر حذف الحساب",
    delete_used: "وجّه اتصالاته إلى حساب آخر أولًا",
    delete_account: "حذف هذا الحساب",
  },
  dialog: {
    title_new: "حساب سحابي جديد",
    title_edit: "تغيير الحساب السحابي",
    subtitle: "تُحفظ الأسرار مشفّرة ولا تُعرض مرة أخرى",
    name: "الاسم",
    kind: "السحابة",
    make: "إنشاء",
    save: "حفظ",
    made: "أُنشئ الحساب",
    saved: "حُفظ الحساب",
    save_failed: "تعذّر حفظ الحساب",
  },
}
