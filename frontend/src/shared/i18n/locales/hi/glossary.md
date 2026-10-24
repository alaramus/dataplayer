# Hindi: terms and style

One word for one thing, across every screen. Add a term here before using a
second word for it.

## Style

- Standard Hindi in Devanagari (`hi`), Quasar's `hi` pack. ECharts has no Hindi
  pack, so a chart's own axis words stay English.
- Write natural Hindi. A label is short and noun-like: “कनेक्शन”, “सहेजें”,
  “रद्द करें”, “हटाएँ”.
- A button or menu item is an action, usually a verb: “सहेजें”, “हटाएँ”,
  “खोलें”, “रद्द करें”.
- Address the reader impersonally where possible: “फ़ाइल सहेजी नहीं जा सकी”.
  Use “आप” only where a full sentence must address one person, and keep it
  consistent within a message.
- Punctuation: “,”, “।”, “?”, “:”, “;”. Quotes are “…” and ‘…’. A dash is “—”,
  an ellipsis is “…”. A colon in a label may be “:”.
- Keep one space between Latin text and Devanagari where it aids reading:
  “PostgreSQL कनेक्शन”, “CSV फ़ाइल”, “{n} पंक्तियाँ”.
- Names a person typed (a table, a connection) stay as they are, in quotes.
- Product and protocol names stay in Latin: PostgreSQL, TimescaleDB, Redis,
  SSH, S3, SQL, CSV, JSON, DuckDB, Docker.
- Do not translate code, identifiers, SQL, key names, enum values, or a
  `{placeholder}`. A placeholder is kept exactly: `{name}`, `{count}`, `{table}`.
  Never add, remove, rename or reorder its braces.
- A message's plural forms are `one | other`, in that order. Hindi “one” is 0
  and 1; everything else is “other”. Keep both forms even when they read alike.
- Never write a bare `@` or `$` in a vue-i18n message.
- Use digits (`5`), not Devanagari numerals.

## Terms

| English | हिन्दी |
| --- | --- |
| connection | कनेक्शन |
| source | स्रोत |
| workspace | वर्कस्पेस |
| catalog | कैटलॉग |
| node | नोड |
| panel | पैनल |
| tab | टैब |
| tab group | टैब समूह |
| rail (tool rail) | टूल रेल |
| bottom panel | निचला पैनल |
| pair (two catalogs side by side) | दोहरा कैटलॉग |
| window | विंडो |
| table | टेबल |
| view | व्यू |
| materialized view | मटीरियलाइज़्ड व्यू |
| relation | रिलेशन |
| schema | स्कीमा |
| database | डेटाबेस |
| column | कॉलम |
| row | पंक्ति |
| index | इंडेक्स |
| constraint | कंस्ट्रेंट |
| primary key | प्राथमिक कुंजी |
| foreign key | फ़ॉरेन की |
| reference (declared) | संदर्भ |
| declared reference | घोषित संदर्भ |
| function | फ़ंक्शन |
| sequence | सीक्वेंस |
| trigger | ट्रिगर |
| extension | एक्सटेंशन |
| hypertable | हाइपरटेबल |
| chunk | चंक |
| key (Redis) | कुंजी |
| key space | कुंजी स्थान |
| file storage | फ़ाइल संग्रहण |
| query | क्वेरी |
| result | परिणाम |
| row view | पंक्ति दृश्य |
| action | क्रिया |
| capability | क्षमता |
| download | डाउनलोड |
| export | निर्यात |
| import | आयात |
| paste | चिपकाएँ |
| copy | कॉपी |
| transfer | स्थानांतरण |
| pipeline | पाइपलाइन |
| link (pipeline) | लिंक |
| run | रन |
| job | जॉब |
| step | चरण |
| dashboard | डैशबोर्ड |
| widget | विजेट |
| metric | मीट्रिक |
| agent | एजेंट |
| chat | चैट |
| message | संदेश |
| prompt | प्रॉम्प्ट |
| search | खोज |
| search index | खोज अनुक्रमणिका |
| share | साझा करें |
| link (share) | लिंक |
| access | पहुँच |
| grant | अनुदान |
| user | उपयोगकर्ता |
| account | खाता |
| superuser | सुपरयूज़र |
| preference | प्राथमिकता |
| theme | थीम |
| terminal | टर्मिनल |
| server | सर्वर |
| service | सेवा |
| template | टेम्पलेट |
| backup | बैकअप |
| report | रिपोर्ट |
| notification | सूचना |
| onboarding | शुरुआती मार्गदर्शन |
| guide | उपयोगकर्ता गाइड |
| freshness | ताज़गी |
| grid | ग्रिड |
| record | रिकॉर्ड |
| content | सामग्री |
| document | दस्तावेज़ |
| archive | संग्रह |
| relationship | संबंध |
| schema form | स्कीमा फ़ॉर्म |
| source operation | स्रोत संचालन |
| refresh | रीफ़्रेश करें |
| save | सहेजें |
| delete | हटाएँ |
| cancel | रद्द करें |
| close | बंद करें |
| open | खोलें |
| settings | सेटिंग्स |
| preferences | प्राथमिकताएँ |
