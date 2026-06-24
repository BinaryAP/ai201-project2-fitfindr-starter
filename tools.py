"""
FitFindr tools.

Three tools, each with a defined interface and its own failure mode:
  - search_listings(description, size, max_price) -> list[dict]
  - suggest_outfit(new_item, wardrobe)            -> str
  - create_fit_card(outfit, new_item)             -> str

The two LLM-backed tools use Groq (llama-3.3-70b-versatile). The Groq client
is created lazily so that search_listings (pure Python) can be imported and
tested without a key or the groq package installed.
"""

import os
import re
import json

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from utils.data_loader import load_listings

_GROQ_MODEL = "llama-3.3-70b-versatile"


def _get_client():
    """Create a Groq client. Raises a clear error if the key is missing."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set. Add it to your .env file.")
    from groq import Groq  # imported lazily on purpose
    return Groq(api_key=api_key)


# ---------------------------------------------------------------------------
# Tool 1: search_listings
# ---------------------------------------------------------------------------
def search_listings(description, size=None, max_price=None):
    """
    Search the mock listings dataset.

    Args:
        description (str): free-text description, e.g. "vintage graphic tee".
        size (str | None): exact size filter, e.g. "M". None = any size.
        max_price (float | None): inclusive price ceiling. None = no ceiling.

    Returns:
        list[dict]: matching listings (each a full listing dict), sorted by
        relevance to `description` (best first). Empty list if nothing matches.

    Failure mode: on no matches OR a data-load error, returns [] (never raises).
    """
    try:
        listings = load_listings()
    except Exception:
        return []

    desc = (description or "").lower()
    keywords = [w for w in re.findall(r"[a-z0-9']+", desc) if len(w) > 2]

    scored = []
    for item in listings:
        # --- size filter ---
        if size:
            if str(item.get("size", "")).strip().lower() != str(size).strip().lower():
                continue
        # --- price filter ---
        if max_price is not None:
            try:
                if float(item.get("price", 0)) > float(max_price):
                    continue
            except (TypeError, ValueError):
                continue
        # --- relevance score ---
        tags = [str(t).lower() for t in (item.get("style_tags") or [])]
        colors = [str(c).lower() for c in (item.get("colors") or [])]
        haystack = " ".join([
            str(item.get("title", "")),
            str(item.get("description", "")),
            str(item.get("category", "")),
            " ".join(tags),
            " ".join(colors),
            str(item.get("brand", "")),
        ]).lower()

        title_words = str(item.get("title", "")).lower()
        desc_words = str(item.get("description", "")).lower()
        score = sum(haystack.count(kw) for kw in keywords)
        score += sum(3 for kw in keywords if kw in title_words)   # title match weighted highest
        score += sum(2 for kw in keywords if kw in desc_words)
        score += sum(1 for kw in keywords if kw in tags)

        # If the user gave no usable keywords, treat every (filtered) item as a match.
        if score > 0 or not keywords:
            scored.append((score, item))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored]


# ---------------------------------------------------------------------------
# Tool 2: suggest_outfit
# ---------------------------------------------------------------------------
def suggest_outfit(new_item, wardrobe):
    """
    Suggest one complete outfit built around `new_item` using the user's wardrobe.

    Args:
        new_item (dict): a listing dict (the item the user is adding).
        wardrobe (dict): {"items": [ ... ]}. May be empty.

    Returns:
        str: a 2-3 sentence styling suggestion.

    Failure mode: missing item -> explanatory string; empty wardrobe -> general
    styling advice (not a crash); LLM/network error -> graceful message string.
    """
    if not new_item:
        return "I couldn't put together an outfit because no item was selected."

    items = []
    if isinstance(wardrobe, dict):
        items = wardrobe.get("items", []) or []

    item_desc = json.dumps(new_item, indent=2) if isinstance(new_item, dict) else str(new_item)

    if items:
        wardrobe_clause = (
            "Here is what the user already owns:\n"
            + json.dumps(items, indent=2)
            + "\nBuild the outfit around pieces they actually have."
        )
    else:
        wardrobe_clause = (
            "The user's wardrobe is empty or unknown. Suggest versatile, easy-to-find "
            "staple pieces (bottoms, shoes, a layer) that would complete the look."
        )

    prompt = (
        "You are a sharp personal stylist. Given a secondhand item and the user's wardrobe, "
        "describe ONE complete outfit in 2-3 punchy sentences. Name specific pieces and one "
        "concrete styling move (cuff, tuck, layer). Conversational, not a product description.\n\n"
        f"New item:\n{item_desc}\n\n{wardrobe_clause}"
    )

    try:
        client = _get_client()
        resp = client.chat.completions.create(
            model=_GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=220,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return (
            "I found the item, but I couldn't generate a styling suggestion right now "
            f"({e}). Try again in a moment, or restate your request."
        )


# ---------------------------------------------------------------------------
# Tool 3: create_fit_card
# ---------------------------------------------------------------------------
def create_fit_card(outfit, new_item):
    """
    Generate a short, shareable social caption for a complete outfit.

    Args:
        outfit (str): the styling suggestion from suggest_outfit.
        new_item (dict): the listing dict the look is built around.

    Returns:
        str: a casual first-person caption (varies between runs).

    Failure mode: empty/blank outfit -> descriptive error string (no crash);
    LLM/network error -> graceful message string.
    """
    if not outfit or not str(outfit).strip():
        return "I couldn't write a fit card yet — there's no outfit to describe."

    if isinstance(new_item, dict):
        item_hint = (
            f"{new_item.get('title', 'this piece')} "
            f"(${new_item.get('price', '?')}, {new_item.get('platform', 'thrifted')})"
        )
    else:
        item_hint = str(new_item)

    prompt = (
        "Write ONE short, casual, first-person social caption (1-2 sentences) for this thrifted "
        "outfit. Lowercase-leaning, a little playful, include exactly one emoji. It should sound "
        "like a real person captioning a post — NOT a product description. No hashtags.\n\n"
        f"Item: {item_hint}\nOutfit: {outfit}"
    )

    try:
        client = _get_client()
        resp = client.chat.completions.create(
            model=_GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=1.0,  # high temperature -> different caption each run
            max_tokens=120,
        )
        return resp.choices[0].message.content.strip().strip('"')
    except Exception as e:
        return f"I couldn't generate a caption right now ({e})."