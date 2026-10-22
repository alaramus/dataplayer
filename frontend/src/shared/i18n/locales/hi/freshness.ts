/** डेटा कितना पुराना है, कितनी बार रीफ़्रेश होता है (shared/freshness)। */
import type { Messages } from "../en"

export const freshness: Messages["freshness"] = {
  live: "लाइव",
  nothing: "कुछ नहीं",
  read_now: "अभी स्रोत से पढ़ा गया।",
  read_ago: "{age} पहले स्रोत से पढ़ा गया।",
  keeps_as_source_says: "यह कनेक्शन उत्तर उतनी देर रखता है जितनी देर स्रोत कहता है।",
  keeps_nothing: "यह कनेक्शन कुछ नहीं रखता: हर पढ़ाई स्रोत तक पहुँचती है।",
  keeps_for: "यह कनेक्शन उत्तर {window} तक रखता है।",
}
