"""
FitFindr planning loop.

run_agent(query, wardrobe) parses a natural-language request, then decides which
tools to call based on what each one returns. It does NOT call all three tools
unconditionally: if search_listings comes back empty, it records an error and
returns early WITHOUT calling suggest_outfit or create_fit_card.

State lives in a single `session` dict that is threaded through every step, so
data found by one tool flows into the next without the user re-entering anything.
"""

import os
import re
import json

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe

_GROQ_MODEL = "llama-3.3-70b-versatile"


def _parse_query(query):
    """
    Turn a free-text request into {description, size, max_price}.

    Tries the LLM first; on any failure falls back to regex so the agent still
    runs offline (and so the no-results branch can be tested without a key).
    """
    fallback = _regex_parse(query)

    try:
        from groq import Groq
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            return fallback
        client = Groq(api_key=api_key)
        prompt = (
            "Extract search parameters from this thrifting request. Reply with ONLY a JSON "
            'object: {"description": str, "size": str|null, "max_price": number|null}. '
            "description is the item being sought (no size/price words).\n\n"
            f"Request: {query}"
        )
        resp = client.chat.completions.create(
            model=_GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=120,
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"^```(json)?|```$", "", raw, flags=re.MULTILINE).strip()
        data = json.loads(raw)
        return {
            "description": data.get("description") or fallback["description"],
            "size": data.get("size"),
            "max_price": (float(data["max_price"]) if data.get("max_price") is not None else None),
        }
    except Exception:
        return fallback


def _regex_parse(query):
    q = query or ""
    price = None
    m = re.search(r"\$?\s*(\d+(?:\.\d+)?)", q)
    if m and re.search(r"(under|below|less than|max|\$|budget)", q, re.IGNORECASE):
        price = float(m.group(1))
    size = None
    m = re.search(r"\bsize\s+([a-z0-9]+)\b", q, re.IGNORECASE)
    if m:
        size = m.group(1).upper()
    else:
        m = re.search(r"\b(XXS|XS|S|M|L|XL|XXL)\b", q)
        if m:
            size = m.group(1)
    # strip size/price phrases to leave a description
    desc = re.sub(r"(under|below|less than|max).{0,8}\$?\s*\d+(\.\d+)?", "", q, flags=re.IGNORECASE)
    desc = re.sub(r"\bsize\s+[a-z0-9]+\b", "", desc, flags=re.IGNORECASE)
    desc = re.sub(r"\$\s*\d+(\.\d+)?", "", desc)
    desc = re.sub(r"\b(i'?m looking for|i want|find me|looking for|a|an)\b", " ", desc, flags=re.IGNORECASE)
    desc = re.sub(r"[.,].*$", "", desc)  # drop trailing "I mostly wear..." clause
    desc = re.sub(r"\s+", " ", desc).strip()
    return {"description": desc or q.strip(), "size": size, "max_price": price}


def run_agent(query, wardrobe=None):
    """
    Run the FitFindr agent on a single query and return the session state.

    Returns a session dict with keys:
        query, search_params, listings, selected_item,
        outfit_suggestion, fit_card, error, log
    """
    session = {
        "query": query,
        "search_params": None,
        "listings": None,
        "selected_item": None,
        "outfit_suggestion": None,
        "fit_card": None,
        "error": None,
        "log": [],
    }

    if wardrobe is None:
        wardrobe = get_example_wardrobe()

    # --- Step 1: parse the request --------------------------------------
    params = _parse_query(query)
    session["search_params"] = params
    session["log"].append(f"Parsed query -> {params}")

    # --- Step 2: search -------------------------------------------------
    results = search_listings(params["description"], params.get("size"), params.get("max_price"))
    session["listings"] = results
    session["log"].append(f"search_listings returned {len(results)} item(s)")

    # --- Branch: stretch retry-with-loosened-constraints ----------------
    # If nothing matched and a size filter was applied, retry once without it.
    if not results and params.get("size"):
        loosened = search_listings(params["description"], None, params.get("max_price"))
        if loosened:
            results = loosened
            session["listings"] = results
            session["log"].append("No size match; retried without size filter and found results.")

    # --- Branch: empty -> error, return early (DO NOT call other tools) -
    if not results:
        session["error"] = (
            f"I couldn't find any listings matching \"{params['description']}\""
            + (f" in size {params['size']}" if params.get("size") else "")
            + (f" under ${params['max_price']:.0f}" if params.get("max_price") else "")
            + ". Try a broader description, a higher price, or removing the size filter."
        )
        session["log"].append("Empty results -> set error, returning early.")
        return session

    # --- Step 3: select + suggest outfit --------------------------------
    session["selected_item"] = results[0]  # top-ranked match flows forward
    session["log"].append(f"Selected: {results[0].get('title')}")

    session["outfit_suggestion"] = suggest_outfit(session["selected_item"], wardrobe)
    session["log"].append("Generated outfit suggestion.")

    # --- Step 4: fit card -----------------------------------------------
    session["fit_card"] = create_fit_card(session["outfit_suggestion"], session["selected_item"])
    session["log"].append("Generated fit card.")

    return session


if __name__ == "__main__":
    print("=" * 60)
    print("TEST 1 — happy path (all three tools)")
    print("=" * 60)
    s = run_agent("I'm looking for a vintage graphic tee under $30, size M. "
                  "I mostly wear baggy jeans and chunky sneakers.")
    for k in ("search_params", "selected_item", "outfit_suggestion", "fit_card", "error"):
        print(f"\n[{k}]\n{s[k]}")

    print("\n" + "=" * 60)
    print("TEST 2 — no results (must error and NOT call other tools)")
    print("=" * 60)
    s2 = run_agent("designer ballgown, size XXS, under $5")
    print("error           :", s2["error"])
    print("selected_item   :", s2["selected_item"])
    print("outfit_suggestion:", s2["outfit_suggestion"])
    print("fit_card        :", s2["fit_card"])
    assert s2["error"] is not None
    assert s2["fit_card"] is None
    assert s2["outfit_suggestion"] is None
    print("\nOK: error path returned early without calling suggest_outfit/create_fit_card.")
