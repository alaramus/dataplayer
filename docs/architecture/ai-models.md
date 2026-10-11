# Models, keys and Jev

Which models the agent and the quick chat may use, whose key pays for them, and
the experimental Jev policy and routing over them. The agent itself — its
tools, its runs and the chat window — is in [ai.md](ai.md). Read this before
adding a model or a provider, or before changing how a key is stored or a model
is chosen.

Decisions here: D140, D156, D157.

## What exists today

The model selector groups models by provider under a hairline. The provider's
heading carries only the key button, whose mark says whether its one key is
configured; it opens the same provider key window, so setting an Anthropic
key, for example, enables every Anthropic model rather than attaching a
secret to one model. The models themselves are one line each, and the field
names the chosen model with no key mark beside it.
Each provider group also offers Jev model selection (D157) when the person's
provider and TypeSafe keys are set, and the top of the list offers Jev across
every provider with a key. Every Jev row carries the one Jev key button and
names its scope in brackets, while a provider's own key lives on its heading.
A conversation remembers its previous model
as fallback. The actual model used is shown on the run.

The experimental Jev change policy (D156) is a fourth conversation policy.
Its choice is disabled until the person saves a verified TypeSafe key in AI
settings. Jev decides each proposed change independently; its denial or failure
prevents the change and appears on the tool step. It never grants connection
access or overrides a read-only connection.

## D140. Models are a curated file; keys belong to the person

OpenAI, Anthropic, DeepSeek and Gemini. Models are a closed JSON list in the
repository — context window, maximum output, reasoning, image input — changed
with a release, validated at startup and in CI, served to the client through the
API. A stored model missing from the file reads as none chosen. One key per
provider per person, encrypted under `CONNECTOR_SECRET_KEY` and never returned,
with Check, which answers for a key as it is typed as well as for the stored
one and keeps neither. The key window links to the page where the provider
issues keys; the address is the server's, sent with each key's state. A conversation is held with the model it names, chosen
in its own composer; the settings choose what a new conversation starts with,
and a model chosen in a composer — an agent chat or a quick one — becomes that
choice as well, in the same commit, so the last model picked anywhere is the
next chat's. A conversation
naming a model the list no longer has falls back to the settings' choice
rather than refusing to answer. Each provider's reasoning must be
carried back inside a tool loop, and a test per provider proves it.

The September 2026 catalog update adds GPT-6 Astra, Sol and Luna, Claude
Opus 5.5, and Gemini 3.7 and 3.8 Flash. It replaces the retired DeepSeek V4
Flash API ID with `deepseek-flash` (V4.1 Flash) and migrates saved settings
and conversation choices to that ID. Historical run records retain the ID
they actually used. The catalog keeps older active models so an existing
selection remains usable. Model IDs, limits and image support were checked
against the [OpenAI model catalog](https://developers.openai.com/api/docs/models),
[Claude models](https://platform.claude.com/docs/en/models/overview),
[Gemini models](https://ai.google.dev/gemini-api/docs/models) and
[DeepSeek models](https://api-docs.deepseek.com/quick_start/pricing/).

Spec: [The application agent](../decisions/2026-09-14-application-agent-design.md)

## D156. Experimental Jev policy decides each change

A conversation may choose Jev as its change policy only after its owner stores
a verified TypeSafe API key. The key uses the same encrypted per-person key store
as the chat model keys; it is never returned. Settings provide Check, replace
and Clear. Clearing a key leaves the conversation's selection visible, but
every later change fails closed until a valid key is stored again. The selector
shows the unavailable choice with a message pointing to AI settings.

Before each changing query or action, the server sends Jev the proposed action,
connection name and bounded preview. A `Noul` answer at least 0.5 allows it;
below 0.5 denies it. Missing answers, network errors and timeouts deny it.
The decision appears as a tool substep. Jev does not override connection access,
read-only connections or the third-party transfer flag. This conversation
policy takes precedence over the person's global allow-all setting.

This experiment pins `langchain-typesafe==0.0.1a3`; its interface is pre-release.
To roll back, revert the dedicated Jev commit. Stored conversations with `jev`
then read as `ask` through `policy_of`; old TypeSafe keys remain encrypted and
inert until explicitly cleared or removed by a later migration.

Spec: [Jev change-policy experiment](../decisions/2026-09-24-jev-change-policy.md)

## D157. Jev may select any compatible model with a configured key

Each model group offers an automatic Jev choice when the person has both that
provider's key and a TypeSafe key, and the top of the list offers one across
every provider with a key. All catalog models of the chosen scope are
candidates for each answer; models without image input are excluded whenever
the conversation has an image, as is any model whose provider has no key. The
prior model stays as fallback, or the first model in the new group if the
person switched providers; the all-providers choice falls back to the current
model when its provider has a key, else the first keyed one. A selection stores the
scope (`all` for every keyed provider) and fallback independently; made in a
conversation that has no model of its own, it pins the fallback it was checked
against, since such a conversation otherwise reads the person's choice. The actual chosen model is recorded on
the run, shown beside its steps, and used for the whole run, its summary, and
its title. A paused run resumes with that same model. Jev sees only the latest
user text, truncated to 16,000 characters, plus the providers in scope and
image presence.
It does not receive attachments, prior messages or tool results for routing.

If Jev fails, returns a model outside the candidates, or its key was removed,
the fallback answers. If the fallback cannot read an image, the first compatible
model of the chosen scope answers. If no compatible model exists, the run is
refused. A server-side key and scope check prevents selecting an unavailable
auto choice through the API; the keyed set is read when the answer starts, so a
key removed after the choice still routes only where a call can go, and the
routed model's key — possibly another provider's — is read after the choice.
The first UI selection warns about provider-wide choice, or every keyed
provider in the all choice, different costs and TypeSafe transfer. Its Don't show again checkbox
uses the same per-user, per-server browser storage pattern as tab groups and
is remembered only when the person confirms.

The classification runs before the answer is recorded, and has a 10-second
limit. It uses the same `langchain-typesafe` dependency as D156, called directly
because its experimental middleware does not carry this application's per-user
key and fallback model. The database stores nullable `auto_provider` fields on
the person's preferences and each conversation; removing this feature requires
reverting the code and downgrading the migration.

Spec: [Jev model routing](../decisions/2026-09-24-jev-model-routing.md)
