# Quick chat and selected text

Date: 2026-09-24. Decision: D158.

The application has an agent chat for acting through connections. A second,
plain chat is needed for ordinary questions. Its Quick chat button on the
workspace rail opens a floating window. Plain conversations have separate
persistent storage from agent conversations and runs, with a shared history
list (D159).

Quick chat calls the selected provider model with text history and no agent,
tools, workspace context or data-source access. It reuses the person's model
provider keys and curated catalog. The first answer titles the conversation
from its question. Messages are encrypted under the same AI content key as
agent messages.
Opening and closing an empty window does not create a history entry. The first
send creates the chat and stores the question before asking the model, so a
failed model call leaves that question available for a follow-up.

Within an agent transcript, selecting message text offers Add to chat, which
quotes it into the current agent draft without sending, and More details,
which opens a new quick conversation and immediately asks for an explanation.
The latter is an explicit transfer of the selected text to the model provider.
The selection menu is attached only to transcript text, not the composer.

A shared frontend opener accepts a plain open or explanation intent. The AI
rail and selection menu use it now; future Data surfaces can use the same
entry point without owning the quick-chat window or the agent conversation.
