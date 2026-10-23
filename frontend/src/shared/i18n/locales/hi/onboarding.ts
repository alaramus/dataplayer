/** स्वागत दौरा (features/onboarding), और गाइड की विंडो (features/guide) तथा ज़ोर से पढ़ने (features/speech) के कुछ शब्द। */
import type { Messages } from "../en"

export const onboarding: Messages["onboarding"] = {
  title: "DataPlayer में आपका स्वागत है",
  intro: "भाषा और एप्लिकेशन का रूप चुनें, फिर एक छोटे दौरे में देखें कि यह क्या कर सकता है: इसके हर मुख्य भाग के लिए एक मौन क्लिप।",
  steps: {
    new_connection: "नया कनेक्शन बनाना",
    tabs: "टैब के साथ काम करना",
    table: "टेबल के साथ काम करना",
    pipelines: "पाइपलाइन के साथ काम करना",
    dashboards: "डैशबोर्ड के साथ काम करना",
    ai_agent: "AI एजेंट के साथ काम करना",
  },
  position: "{total} में से चरण {n}",
  start: "दौरा शुरू करें",
  finish: "समाप्त करें",
  next: "आगे",
  skip_tour: "दौरा छोड़ें",
  skip: "छोड़ें",
  mark_failed: "दौरे को देखा हुआ चिह्नित नहीं किया जा सका",
  close_title: "स्वागत दौरा बंद करें?",
  close_message: "दौरा अपने आप फिर नहीं खुलेगा। आप इसे कभी भी प्राथमिकताओं में “स्वागत दौरा” के अंतर्गत फिर से चला सकते हैं।",
  close_confirm: "दौरा बंद करें",
  keep_watching: "देखते रहें",
  guide: {
    title: "उपयोगकर्ता गाइड",
    not_a_page: "यह लिंक गाइड के किसी पृष्ठ पर नहीं ले जाता",
    read_failed: "गाइड का यह पृष्ठ पढ़ा नहीं जा सका",
  },
  speech: {
    listen: "सुनें",
    stop: "ज़ोर से पढ़ना बंद करें",
    browser_default: "ब्राउज़र डिफ़ॉल्ट",
  },
}
