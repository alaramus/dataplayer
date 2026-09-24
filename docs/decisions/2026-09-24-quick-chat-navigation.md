# Quick chat navigation

Date: 2026-09-24. Decision: D159.

Quick chat is useful outside the AI space, so its launch button belongs to the
workspace tool rails. It creates a plain conversation in the existing floating
window. The window should look and behave like the agent conversation for
reading and composing, while retaining a direct model call and separate storage.

The window no longer manages its own history. Quick conversations appear in
the main AI chat history with a distinct icon; selecting a saved one opens it
in the quick-chat window. Deletion remains on the history row with confirmation.
This keeps one place to find conversations while preserving the separate agent
and plain-chat data models. The shared opener also accepts a saved chat ID, so
other application surfaces can open one without depending on the AI space.
