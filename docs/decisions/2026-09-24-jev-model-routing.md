# Jev model routing within a provider

Date: 2026-09-24. Decision: D157.

The agent already groups curated models by provider and stores the selected
chat model. Jev's TypeSafe key is stored separately for its change policy
(D156). Model routing reuses that key without changing the change policy.

Each provider group offers "Choose with Jev". Selecting it enables Jev for all
models currently listed under that provider, without a second model allowlist.
The model previously selected remains the fallback; when switching to another
provider's group, its first catalog model becomes the fallback. Both the
provider and the fallback are stored. New conversations inherit the settings'
selection, while a conversation with its own model keeps its own selection.

The first selection opens the existing confirmation window, explaining that
models may have different costs and capabilities and that the latest request
will be sent to TypeSafe. "Don't show again" is saved in browser storage scoped
to the server and user, only after confirmation, as for opening tab groups.
The choice is disabled until both keys are present.

At the start of an answer, Jev classifies the latest user text against every
compatible model of the selected provider. Images exclude models that cannot
read them, including when an earlier message in the conversation has an image.
The classifier receives no attachment content, earlier messages, connection
results or provider secrets. One model is selected for the entire run. Its
catalog entry sets output and summarization limits, its key calls the chat
provider, and its id is recorded on the run. The transcript shows that model.

A missing TypeSafe key, timeout, service error or invalid choice uses the saved
fallback. If the fallback is incompatible with an image, use the first
compatible model. The run records this as its Thinking step title. The
selection is stable when the run pauses and resumes. No compatible model means
the request is refused before an answer begins.

The integration calls `TypeSafeClassifier` directly rather than using the
experimental `ModelRouterMiddleware`: the application owns per-person keys,
fallback selection, run records and context limits. It needs those decided
before building the LangChain agent. A later release can reconsider middleware
when those boundaries are supported.
