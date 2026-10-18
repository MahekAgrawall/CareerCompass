# Prompt library

Every AI call in CareerCompass reads its wording from here instead of carrying an
inline string, so the prompts can be reviewed, diffed and tuned without editing
Python.

## Layout

```
prompts/
  system/<call>.md   the persona and standing rules — sent as the system instruction
  user/<call>.md     the task and the values for one specific call
```

- `system/` files are the parts that never change between calls: who the model
  is, what it must and must not do, and (for the roadmap) the JSON schema it has
  to answer with.
- `user/` files are the per-call half: the values injected for this candidate and
  this role.

## Placeholders

Templates use `$name` placeholders (`string.Template`), not `{}`. That keeps the
JSON schema in `system/roadmap.md` readable as literal braces and removes the
`{{`/`}}` doubling an f-string needed. Values are substituted with
`Template.substitute`, so a placeholder that has no value fails loudly in tests
rather than shipping a prompt containing a literal `$role_title`.

## Calls

| Call | System | User |
| --- | --- | --- |
| Roadmap generation | `system/roadmap.md` | `user/roadmap.md` |
| Role-match explanation | `system/match_explanation.md` | `user/match_explanation.md` |
| Roadmap copilot | `system/copilot.md` | the candidate's live message |
| Listing classification | `system/classify_listing.md` | `user/classify_listing.md` |

Loading and rendering live in `services/prompts.py`.

`system/classify_listing.md` is the one template whose *contents* are partly generated:
the declared role vocabulary is rendered into it from `config.CANONICAL_ROLES` by
`services.ai_service.classification_vocabulary()`. The list the model chooses from and
the list the validator accepts are therefore the same list by construction — a
vocabulary that could drift from its own validator would let an undeclared role be
stored, or make a declared one look invalid.

## Versioning

`prompts.fingerprint(*paths)` returns a short, stable hash of one or more templates, and a
generated roadmap is saved with the fingerprint of `system/roadmap.md` +
`user/roadmap.md` beside the model id. Prompts are edited as files, so a diff alone
cannot tell you which wording was live when a given plan was produced; the stored
fingerprint can.

A stored listing classification records the same fingerprint (of the classification
pair) beside the advert's content hash and the model id, and is only reused when all
three still match. Editing the classification wording is therefore enough to have every
listing read again on its next page view, without deleting anything.

## Untrusted values

Values substituted into a prompt are scrubbed first (`services/sanitize.py`): the
candidate's answers arrive back from the browser, and the copilot's land in a *system*
instruction. Free text is flattened to one length-capped line; skills and interests are
reduced to plain labels. Add a new placeholder with a value that came from a client and
it should go through the same scrubbing.
