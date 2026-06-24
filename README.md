# FitFindr

A multi-tool AI agent that finds secondhand clothing and figures out how to wear
it. Given a natural-language request, FitFindr searches mock listings, builds an
outfit around the best match using the user's wardrobe, and writes a shareable
caption — while handling the cases where a tool finds nothing or fails.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file in the repo root (already gitignored):

```
GROQ_API_KEY=your_key_here
```

Run the tests, the agent, and the app:

```bash
pytest tests/
python agent.py        # prints a happy-path run and a no-results run
python app.py          # open the URL printed in the terminal
```

## Tool Inventory

| Tool | Inputs | Output | Purpose |
|------|--------|--------|---------|
| `search_listings` | `description (str)`, `size (str \| None)`, `max_price (float \| None)` | `list[dict]` of full listings, ranked by relevance (`[]` if none) | Filter the listings dataset by size/price and rank by match to the description |
| `suggest_outfit` | `new_item (dict)`, `wardrobe (dict)` | `str` (2–3 sentence styling suggestion) | Build one complete outfit around the found item using the user's wardrobe |
| `create_fit_card` | `outfit (str)`, `new_item (dict)` | `str` (short caption, varies per run) | Turn the outfit into a casual, shareable social caption |

The documented inputs/outputs match the actual function signatures in `tools.py`.

## How the Planning Loop Works

`run_agent(query, wardrobe)` in `agent.py` runs conditional logic, not a fixed
sequence:

1. `_parse_query` extracts `{description, size, max_price}` (LLM with a regex fallback).
2. Call `search_listings`.
3. **If results are empty and a size was set**, retry once without the size filter.
4. **If still empty**, set `session["error"]` and **return early** — `suggest_outfit` and `create_fit_card` are never called on empty input.
5. Otherwise set `selected_item = results[0]`, call `suggest_outfit`, then `create_fit_card`.

Because step 4 short-circuits, the agent's behavior genuinely differs between a
matchable query (three tool calls) and an impossible one (one tool call + error).

## State Management

A single `session` dict is created in `run_agent` and threaded through every
step: `query`, `search_params`, `listings`, `selected_item`,
`outfit_suggestion`, `fit_card`, `error`, `log`. The exact listing dict from
`search_listings` is stored in `selected_item` and passed directly into
`suggest_outfit`; that string is stored in `outfit_suggestion` and passed into
`create_fit_card`. The user never re-enters anything and no values are hardcoded
between steps — printing `session["selected_item"]` shows the same dict that
went into `suggest_outfit`.

## Error Handling (per tool, with examples)

- **`search_listings` — no matches.** Returns `[]`. The loop sets a specific
  message and stops.
  Example: `search_listings("designer ballgown", "XXS", 5)` → `[]`; the agent
  replies *"I couldn't find any listings matching 'designer ballgown' in size
  XXS under $5. Try a broader description, a higher price, or removing the size
  filter."* and does not call the other tools.
- **`suggest_outfit` — empty wardrobe.** Returns general staple-based advice
  instead of crashing.
  Example: `suggest_outfit(item, get_empty_wardrobe())` returns a usable styling
  string built around versatile pieces.
- **`create_fit_card` — empty outfit.** Returns a descriptive error string.
  Example: `create_fit_card("", item)` → *"I couldn't write a fit card yet —
  there's no outfit to describe."* (a string, not an exception).
- **LLM/network errors** in either LLM tool are caught and returned as a plain
  message so the agent stays usable.

## Spec Reflection

- **One way the spec helped:** writing the tool interfaces and failure modes in
  `planning.md` before coding meant each function had a defined contract, so the
  planning loop only had to branch on `[]` vs non-empty rather than guess at
  shapes.
- **One way implementation diverged:** the spec models the planner calling
  `search_listings` directly on a description, but real queries are full
  sentences, so I added a `_parse_query` step (with a regex fallback) to turn
  the sentence into structured parameters first. This wasn't a named tool in the
  original spec; I added it because the agent was otherwise feeding entire
  sentences into the keyword matcher and ranking poorly.

## AI Usage

- **`search_listings`:** I gave Claude the Tool 1 spec block from `planning.md`
  (inputs, return value, failure mode) and asked it to implement filtering with
  `load_listings()`. I overrode its first version, which only substring-matched
  the title — I changed scoring to also weight `style_tags` and to return `[]`
  cleanly on a data-load error, then verified with the price/size/empty tests.
- **Planning loop:** I gave Claude the Architecture diagram plus the Planning
  Loop and State Management sections and asked for `run_agent`. Its draft called
  all three tools unconditionally; I revised it to return early on empty results
  and to thread one shared `session` dict instead of returning loose tuples.

## Demo

`python agent.py` runs both a complete three-tool interaction and the
no-results error path back to back, which mirrors the demo video flow.