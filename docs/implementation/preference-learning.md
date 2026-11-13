# On-demand preference proposals

The user explicitly requests collection from selected messages in the current
role. There is no background learner and no extra model call on ordinary chat.
`memory_mode: off` refuses collection and confirmation before any source text is
sent to a provider. Existing candidates can still be rejected or deleted.

`PreferenceLearningStore(existing_role_database, role_scope, provider=...,
is_scope_current=...)` exposes:

- `collect(request_id, source_message_ids)` returns a durable request with
  `status`, `error`, `candidates`, and `automatic_learning: false`.
- `list(limit=50)` returns candidates after reconciling deletion and forgetting.
- `decide(candidate_id, "confirm" | "reject" | "delete")` changes an owner's
  candidate. Only confirmation inserts a memory, once, with provenance in source.
- `correct(candidate_id, new_source_message_id, exact_quote)` removes the old
  confirmed memory and creates a pending replacement. It returns
  `previous_source_message_id`; the host clears prior chat context while keeping
  the correction's new source. Confirmation is still a separate action.
- `reconcile()` redacts forgotten or stale candidates; invoke before export or
  after memory changes when no list request will immediately follow.
- `cancel_generating()` invalidates in-flight requests. The host must also drain
  complete collect operations before deleting a role, and evict its cached store.

The typed provider receives `PreferenceRequest(request_id, role_scope, sources)`.
Each `PreferenceSource` contains its actual user message id, text and SHA256.
It returns `PreferenceProviderReply(tuple[PreferenceSuggestion], provider_id)`;
each suggestion has `source_message_id` and `exact_quote` only.

Only actual `user/chat` messages in the bound database are eligible. Collection
is bounded to 12 messages, 3000 characters each and 12000 total. A suggestion must
be a complete original line of at most 300 characters and begin with supported
explicit Chinese preference, address or communication-boundary wording. The
module never accepts a model's rewritten fact, assistant statement, vision
observation, invented source or truncated clause. This conservative syntax does
not prove semantic truth or resolve every quoted/fictional context. Owner review
remains mandatory. Unsupported wording can use the existing manual-memory flow.

The core accepts at most 10 suggestions per call; the host's structured adapter
currently asks for at most six. The ledger bounds candidates to 200 and requests
to 1000 per role, and existing memory remains capped at 60 entries. No external
actions or arbitrary code are available. Missing provider reports `unavailable`;
malformed, changed or failed provider results do not become memories.

Immediately before confirmation, source identity, exact digest, original line
and forgetting ledger are checked in a SQLite transaction. Pending or rejected
material with missing/changed sources is redacted. Forgotten candidates are
redacted even if a manual memory endpoint performed the deletion. A confirmed
candidate remains valid after chat is cleared while its actual memory still
exists; deletion or editing of that memory invalidates the old candidate. A
repeated confirmation cannot reconstruct a missing memory. Database connections
use `mode=rw` so stale stores cannot create a deleted role database.

Normal polling performs bounded SQLite reconciliation, without model inference.
Actual device/model latency and UI performance require host measurements; this
module makes no claim of an advanced adaptive learning engine or better model
quality. Provider transmission already in flight cannot be recalled by toggling
memory off; its late result is refused.

Verification: `tests/test_preference_learning.py` has 27 actual SQLite tests,
including 216 bounded traces with 648 Store actions. These check confirmation,
forgetting, cancellation and memory-off safety, not whole-program correctness or
semantic preference extraction. `tests/test_rebuild_http.py` covers real owner
HTTP routes with explicit synthetic model and face-engine fixtures. Real-model
checks are separately maintained by the host agent.
