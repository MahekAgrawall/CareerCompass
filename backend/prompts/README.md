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

Loading and rendering live in `services/prompts.py`.
