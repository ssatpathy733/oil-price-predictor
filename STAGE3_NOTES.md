# Stage 3: assistant transparency, previews, disclaimers, history

Owner: Scarlett. Files changed: `index.html`, `api/main.py`.

## What was added

| Feature | Where | Guideline (Amershi et al. 2019) |
|---|---|---|
| **Preview before applying.** When the assistant suggests slider values, the app runs `/forecast` on them without moving the sliders. It draws a dashed blue "preview" fan on the main chart and lists in plain words how the chart would change (midpoint, range width, biggest driver). **Apply** or **Dismiss**. You can turn this off with a checkbox, which goes back to the old direct-apply flow. | `index.html`: `drawPreview`, `clearPreview`, `explainChange` | G16 convey consequences of user actions, G11 make clear why the system did what it did |
| **Unusual-scenario disclaimer (rule-based).** Each slider value is placed in its historical 20-day percentiles from `/spec`. Outside p5–p95 counts as *unusual*. Outside p1–p99, or two or more unusual factors at once, counts as *highly unlikely*. A banner explains this and says the model still shows its best estimate. This works for manual slider moves too, and appears inside the preview. | `assessScenario`, `renderRarity` | G2 make clear how well the system can do, G4 show contextually relevant information |
| **Unusual-event disclaimer (LLM).** `/ask` now returns `plausibility` (`typical`/`unusual`/`extreme`) and `plausibility_note`. The assistant never refuses; it flags the event and still gives its best estimate. | `api/main.py` system prompt, `#ask-plausibility` | G2 |
| **Starting points.** Four example questions are shown before the first question is asked. | `STARTERS`, `renderStarters` | G1 make clear what the system can do |
| **Follow-up suggestions.** `/ask` returns 2–3 `follow_ups`, shown as clickable chips. | `#ask-followups` | G1, G7 support efficient invocation |
| **Clarifying question.** For vague input ("something bad happens"), `/ask` returns `clarifying_question` instead of guessing analogs. | `#ask-clarify` | G10 scope services when in doubt |
| **Question history / log.** Each question is logged with its time, mode, answer, analogs, suggestion, slider state before and after, outcome (applied / dismissed / expired / none / error), plausibility, and rating. You can **restore** the sliders from any entry or **ask it again**. The log is saved in `localStorage` (last 50 entries) and can be **downloaded as JSON**, which is useful for pilot testing. | `assistantLog`, `renderLog` | G12 remember recent interactions |
| **Conversation context.** The last 4 turns *from the current browser session* are sent to `/ask` as `conversation`, so "what if it's twice as large?" makes sense. | `AskRequest.conversation` | G12 |
| **Answer feedback.** 👍/👎 on each answer, stored in the log. | `#ask-feedback` | G15 encourage granular feedback |

Also fixed: in `/ask`, when Gemini's `response.parsed` was empty, the fallback returned a model object, not a dict, so `.pop()` crashed. It now returns a dict.

## Integration notes for Diya (Stage 2: undo/redo, stop)

* **Undo/redo:** every assistant-driven slider change (Apply, Restore from history) goes through `applyScenario(next, source)`. That function fires a `scenario:applied` event on `document` with `{before, after, source}`, where each state is `{sliders, era}`. Your undo stack can listen without editing Stage 3 code:
  ```js
  document.addEventListener("scenario:applied", (e) => undoStack.push(e.detail.before));
  ```
  Manual slider moves and the Reset button don't use it yet. If you want one code path, route them through `applyScenario` too.
* **Stop button:** the `fetch(`${API}/ask`)` call in the submit handler is where an `AbortController` signal goes. If you abort, the `catch` block logs the entry with outcome `error`. You may want to check for `AbortError` and use outcome `"stopped"` instead (also add it to `OUTCOME_TEXT`).
* Both of us edited the `ask-form` submit handler, so expect a merge conflict there. Keep the Stage 3 version as the base and add your abort signal and undo hooks.

## Testing locally

```bash
uvicorn api.main:app --reload --port 8000
# open http://localhost:8000/?api=http://localhost:8000
```
The new `?api=` query parameter points the page at a local backend. Without it, the page uses the Render URL as before.
The new `/ask` fields all have defaults, so the frontend still works if the deployed backend hasn't been updated yet. You just won't see the plausibility, follow-up, or clarifying-question features until it is.
