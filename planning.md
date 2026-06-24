# FitFindr — Planning

## A Complete Interaction

FitFindr takes a natural-language thrifting request and runs three tools in
sequence to go from query to a shareable caption. A request like *"vintage
graphic tee under $30, size M, I wear baggy jeans"* triggers `search_listings`
first; its top result flows into `suggest_outfit`, whose suggestion flows into
`create_fit_card`. If `search_listings` returns nothing, the agent reports what
failed and stops — it never calls `suggest_outfit` with empty input.

---

## Tools

### Tool 1 — `search_listings(description, size, max_price)`
- **What it does:** filters the mock listings dataset and ranks matches by relevance to `description`.
- **Inputs:**
  - `description` (str) — free text describing the wanted item, e.g. `"vintage graphic tee"`.
  - `size` (str | None) — exact size filter, e.g. `"M"`. `None` means any size.
  - `max_price` (float | None) — inclusive price ceiling. `None` means no ceiling.
- **Returns:** `list[dict]` — each dict is a full listing (`id, title, description, category, style_tags, size, condition, price, colors, brand, platform`), sorted best-match first. Empty list if nothing matches.
- **Failure mode:** no matches → returns `[]` (never raises). Data-load error → also returns `[]`. The agent treats `[]` as a stop condition.

### Tool 2 — `suggest_outfit(new_item, wardrobe)`
- **What it does:** asks the LLM to build one complete outfit around `new_item` using pieces in `wardrobe`.
- **Inputs:**
  - `new_item` (dict) — a listing dict (the item being added).
  - `wardrobe` (dict) — `{"items": [...]}`; may be empty.
- **Returns:** `str` — a 2–3 sentence styling suggestion naming specific pieces and one concrete styling move.
- **Failure mode:** missing item → explanatory string. Empty wardrobe → general staple-based advice instead of a crash. LLM/network error → graceful message string.

### Tool 3 — `create_fit_card(outfit, new_item)`
- **What it does:** turns the outfit into a short, casual, first-person social caption.
- **Inputs:**
  - `outfit` (str) — the suggestion from `suggest_outfit`.
  - `new_item` (dict) — the listing the look is built around.
- **Returns:** `str` — a 1–2 sentence caption with one emoji. Uses temperature 1.0 so output varies per run.
- **Failure mode:** empty/blank `outfit` → descriptive error string (no crash). LLM/network error → graceful message string.

---

## Planning Loop (conditional logic)

1. **Parse.** `_parse_query(query)` extracts `{description, size, max_price}` (LLM with a regex fallback). Store in `session["search_params"]`.
2. **Search.** Call `search_listings(description, size, max_price)`. Store the list in `session["listings"]`.
3. **Branch — retry (stretch).** If results are empty AND a `size` was set, retry once without the size filter; if that finds items, keep them and log the adjustment.
4. **Branch — empty.** If still empty, set `session["error"]` to a specific message and **return immediately**. Do not call `suggest_outfit` or `create_fit_card`.
5. **Select.** Set `session["selected_item"] = results[0]` (top-ranked).
6. **Suggest.** Call `suggest_outfit(selected_item, wardrobe)`; store in `session["outfit_suggestion"]`.
7. **Card.** Call `create_fit_card(outfit_suggestion, selected_item)`; store in `session["fit_card"]`.
8. Return `session`.

The behavior changes with input: an impossible query terminates at step 4; a
matchable query runs all three tools. Tools are never called in a fixed sequence
regardless of context.

---

## State Management

A single `session` dict is created at the start of `run_agent` and threaded
through every step. Keys: `query`, `search_params`, `listings`,
`selected_item`, `outfit_suggestion`, `fit_card`, `error`, `log`. The exact dict
returned by `search_listings` is stored in `selected_item` and passed straight
into `suggest_outfit`; that tool's string output is stored and passed into
`create_fit_card`. Nothing is re-entered by the user and no values are hardcoded
between steps.

---

## Architecture

```
User query
    │
    ▼
Planning Loop ───────────────────────────────────────────────┐
    │                                                         │
    ├─► _parse_query(query) → {description, size, max_price}  │
    │                                                         │
    ├─► search_listings(description, size, max_price)         │
    │       │ results == []                                   │
    │       ├──► (stretch) retry without size filter          │
    │       │      │ still []                                 │
    │       │      ├──► [ERROR] set session["error"] → return │
    │       │                                                 │
    │       │ results == [item, ...]                          │
    │       ▼                                                 │
    │   Session: selected_item = results[0]                   │
    │       │                                                 │
    ├─► suggest_outfit(selected_item, wardrobe)               │
    │       │                                                 │
    │   Session: outfit_suggestion = "..."                    │
    │       │                                                 │
    └─► create_fit_card(outfit_suggestion, selected_item)     │
            │                                                 │
        Session: fit_card = "..."                             └─ error path returns here
            │
            ▼
        Return session  →  app.py maps to 3 output panels
```

---

## AI Tool Plan

- **Tool 1 (`search_listings`) — Claude.** Input: the Tool 1 spec block above (inputs, return, failure mode). Ask it to implement using `load_listings()` from the data loader. Verify: filters on all three params, ranks by relevance, returns `[]` (no exception) on no match. Test with 3 queries before wiring.
- **Planning loop — Claude.** Input: the Architecture diagram + the Planning Loop and State Management sections. Verify: branches on the `search_listings` result, writes to the `session` dict, and does NOT call all three tools unconditionally. Confirm the empty-results path returns before `suggest_outfit`.
- **LLM tools (2 & 3) — Claude.** Input: each tool's spec block. Verify: empty-wardrobe and empty-outfit cases return strings, and `create_fit_card` uses high temperature so output varies.

---

## Complete Interaction Walkthrough

Query: *"I'm looking for a vintage graphic tee under $30, size M. I mostly wear baggy jeans and chunky sneakers."*

1. `_parse_query` → `{"description": "vintage graphic tee", "size": "M", "max_price": 30.0}`.
2. `search_listings("vintage graphic tee", "M", 30.0)` → list of M-size tees ≤ $30, ranked. `selected_item = results[0]` (e.g. the faded band tee, $22, Depop).
3. `suggest_outfit(selected_item, wardrobe)` → e.g. "Pair it with your wide-leg jeans and platform Docs; cuff the sleeves once."
4. `create_fit_card(suggestion, selected_item)` → e.g. "thrifted this faded band tee for $22 and it was made for my wide-legs 🖤".
5. The user sees the listing, the outfit, and the caption in the three panels.

---

## Error Handling

| Tool | Failure | What the agent does |
|------|---------|---------------------|
| `search_listings` | no matches | Returns `[]`; loop sets a specific `error` ("couldn't find X in size M under $30 — try a broader description / higher price / no size") and stops before other tools. |
| `search_listings` | size too narrow (stretch) | Retries once without the size filter and tells the user the filter was loosened. |
| `suggest_outfit` | empty wardrobe | Generates general staple-based styling advice instead of crashing. |
| `suggest_outfit` | missing item / LLM error | Returns an explanatory string; the agent surfaces it rather than failing. |
| `create_fit_card` | empty outfit string | Returns a descriptive error string, not an exception. |
| `create_fit_card` | LLM error | Returns a graceful "couldn't generate a caption right now" message. |