# Quick chat navigation

Date: 2026-09-24. Decision: D159.

Quick chat is useful outside the AI space, so its launch button belongs to the
workspace tool rails. It opens a local draft in the existing floating window;
the conversation enters history on its first send. The window should look and behave like the agent conversation for
reading and composing, while retaining a direct model call and separate storage.

The window no longer manages its own history. Quick conversations appear in
the main AI chat history with the same row and actions as agent conversations:
pin, move to project and archive. Both kinds share the settings archive, where
they can be restored or permanently deleted. Their rows do not reveal which
kind of chat they are; selecting one opens the corresponding chat surface.
This keeps one place to find conversations while preserving the separate agent
and plain-chat data models. The shared opener also accepts a saved chat ID, so
other application surfaces can open one without depending on the AI space.
