# Jev change-policy experiment

Date: 2026-09-24. Decision: D156.

The existing change selector gives a person three policies for a conversation:
read only, ask, and allow. This experiment adds Jev as a fourth. Jev makes a
fresh decision for every proposed change, using the `TypeSafeClassifier` added
to LangChain. It is a classifier, not the model that writes the agent's answer.

## User flow

AI settings offer a TypeSafe (Jev) key. Check sends a harmless classifier
request. Save verifies the key before storing it encrypted per person. Until a
key is stored, the Jev choice remains visible but disabled in the conversation
selector. The disabled choice names AI settings. Removing the key does not
silently change a conversation's policy: its next proposed change is refused
and the tool step says Jev was unavailable.

## Decision point

The existing server-side `confirm_change` path is the decision point for both
SQL changes and source actions. After permission, read-only and transfer checks,
it sends Jev the action sentence, connection name and a bounded preview. A
probability of at least 0.5 allows execution; every other result denies it.
Exceptions and missing answers deny it as well. The tool step records allowed,
declined or unavailable. No user approval card appears in this mode.

The connection's access and execution policy, and its third-party transfer
setting, remain authoritative. Jev's policy takes precedence over the global
allow-all preference. Jev sees the proposed change and possibly source data in
its preview, so the existing transfer permission is required before it runs.

## Experimental boundary and rollback

Pin `langchain-typesafe==0.0.1a3`, a pre-release integration. Keep its use in
the AI package and call it inside the existing change gate rather than adding
the experimental Auto Mode middleware, which would introduce a second decision
path. Revert the dedicated implementation commit to remove the experiment.
The existing `policy_of` fallback then interprets stored `jev` values as `ask`;
encrypted TypeSafe keys are left unused, and may later be deleted with a data
migration. No database schema rollback is needed.

This experiment accepts Jev's binary judgment as the user's chosen approval
policy. The 0.5 threshold is deliberately simple for evaluation and should be
revisited with real decision examples before treating it as a calibrated safety
boundary.
