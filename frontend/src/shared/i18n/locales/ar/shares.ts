/** روابط المشاركة وطلبات الوصول (features/shares). */
import type { Messages } from "../en"

export const shares: Messages["shares"] = {
  this_connection: "هذا الاتصال",
  to_this_connection: "هذا الاتصال",
  to_this_node: "هذه العقدة",
  named: "{name}",
  levels: {
    read: "قراءة",
    write: "كتابة",
    structure: "بنية",
  },
  requests: {
    asked: "{person} يطلب الوصول إلى {connector}",
    approved: "{person} منحك وصولًا بمستوى {level} إلى {connector}",
    declined: "{person} لم يفتح الوصول إلى {connector}",
  },
  attention: {
    through_connection: "عبر رابط إلى الاتصال",
    through_node: "عبر رابط إلى {node}",
    open: "فتح",
  },
  recipients: {
    none_available:
      "لا توجد حسابات نشطة أخرى متاحة. اطلب من المسؤول إنشاء حساب أو تمكينه، ثم أعد فتح «مشاركة».",
    all_have_access:
      "كل الحسابات النشطة الأخرى لديها وصول بالفعل. غيّر مستويات وصولها في تبويب الأذونات في الاتصال.",
  },
  asking: {
    heading: "بانتظار إجابة",
    asked_for: "طلب {what}",
    give_access: "منح الوصول",
    decline: "قل لا. سيُبلَّغون، دون سبب.",
    answer_failed: "تعذّرت الإجابة على ذلك الطلب",
  },
  grants: {
    nobody: "لا أحد غيرك يمكنه الوصول إلى هذا الاتصال",
    revoke: "سحب هذا الوصول",
    change_failed: "تعذّر تغيير ذلك الوصول",
    revoke_failed: "تعذّر سحب ذلك الوصول",
  },
  dialog: {
    title: "مشاركة — {name}",
    link_failed: "تعذّر إنشاء هذا الرابط",
    link_label: "رابط إلى هذا العرض",
    copy_link: "نسخ هذا الرابط",
    link_copied: "تم نسخ الرابط",
    copy_refused: "هذا المتصفح لم يسمح بنسخ الرابط",
    link_note:
      "كل من سجّل الدخول وله وصول إلى {connector} يفتح الصفوف نفسها بالمرشّحات نفسها. ويُعرض لغيره ما هو ومن شاركه، لا أكثر.",
    recipients_failed: "تعذّر تحميل المستلمين ووصولهم. حاول من جديد.",
    retry: "إعادة المحاولة",
    person: "الشخص",
    may: "يمكنه",
    give_access: "منح الوصول",
    give_failed: "تعذّر منح ذلك الوصول",
    whole_connection: "الوصول إلى الاتصال {connector} كله، لا إلى {node} وحده.",
    whole_connection_unnamed: "الوصول إلى الاتصال كله، هذا الاتصال، لا إلى {node} وحده.",
    other_links: "روابط أخرى إلى هذا الاتصال",
    not_opened: "لم يُفتح بعد",
    opened_by: "فتحه {people}",
    delete_link: "حذف هذا الرابط. ولا يسحب وصول أحد.",
    delete_failed: "تعذّر حذف ذلك الرابط",
  },
  landing: {
    title: "عرض مشترك",
    no_access: "شارك {person} {node} من الاتصال {connector}. ليس لديك وصول إليه بعد.",
    requested: "تم سؤال مالك {connector}. وستُبلَّغ عندما يجيب.",
    missing: "هذا الرابط غير موجود، أو حُذف.",
    old: "أُنشئ هذا الرابط بإصدار أقدم من التطبيق ولم يعد يمكن فتحه.",
    gone: "{node} لم يعد في {connector}. افتح الاتصال لترى ما هو موجود الآن.",
    disabled: "{connector} مغلق، لذا لا يمكن قراءة شيء منه.",
    open_failed: "تعذّر فتح هذا الرابط",
    request_failed: "تعذّر إرسال ذلك الطلب",
    request_access: "طلب الوصول",
    to_workspace: "الانتقال إلى مساحة العمل",
  },
}
