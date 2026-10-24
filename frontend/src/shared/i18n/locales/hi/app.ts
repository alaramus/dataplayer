/** Words that belong to no one screen: sign-in, the language, the themes. */
import type { Messages } from "../en"

export const common: Messages["common"] = {
  back_to_workspace: "वर्कस्पेस पर वापस जाएँ",
}

export const language: Messages["language"] = {
  label: "भाषा",
  browser: "ब्राउज़र की भाषा",
  browser_hint: "इस ब्राउज़र द्वारा माँगी गई भाषा, या अंग्रेज़ी",
}

export const auth: Messages["auth"] = {
  sign_in: "साइन इन करें",
  email: "ईमेल",
  password: "पासवर्ड",
  email_required: "ईमेल आवश्यक है",
  password_required: "पासवर्ड आवश्यक है",
  checking_server: "सर्वर की जाँच हो रही है…",
  retry_connection: "कनेक्शन फिर से आज़माएँ",
  sign_in_failed: "साइन इन नहीं हो सका। ईमेल और पासवर्ड जाँचें।",
  welcome_tagline: "आपके हर डेटा स्रोत के लिए एक ही जगह",
}

export const theme: Messages["theme"] = {
  label: "थीम",
  light: "हल्का",
  paper_light: "पेपर हल्का",
  paper_light_hint: "कांस्य रंग की आभा वाला गर्म हल्का पेपर",
  dark: "गहरा",
  paper: "पेपर गहरा",
  paper_hint: "कांस्य रंग की आभा वाला गर्म गहरा पेपर",
  midnight: "मध्यरात्रि",
  midnight_hint: "सबसे मंद: बर्फ़ीले नीले रंग की आभा वाला लगभग काला नेवी",
  dark_blue: "गहरा नीला",
  dark_blue_hint: "सायन रंग की आभा वाला गहरा नेवी",
  dark_purple: "गहरा बैंगनी",
  dark_purple_hint: "गुलाबी और सायन आभा वाला बैंगनी नियोन",
  system: "सिस्टम",
  system_hint: "ऑपरेटिंग सिस्टम के अनुसार हल्का या गहरा",
  switch_to: "{theme} पर स्विच करें",
}
