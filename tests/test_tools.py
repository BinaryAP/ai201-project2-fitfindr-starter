from tools import search_listings, suggest_outfit, create_fit_card


# --- search_listings -------------------------------------------------------
def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list)
    assert len(results) > 0


def test_search_empty_results():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []          # empty list, no exception


def test_search_price_filter():
    results = search_listings("tee", size=None, max_price=20)
    assert all(item["price"] <= 20 for item in results)


def test_search_size_filter():
    results = search_listings("", size="M", max_price=None)
    assert all(str(item["size"]).upper() == "M" for item in results)


# --- suggest_outfit failure mode (no network needed) -----------------------
def test_suggest_outfit_missing_item():
    msg = suggest_outfit(None, {"items": []})
    assert isinstance(msg, str) and len(msg) > 0   # explanatory string, no crash


# --- create_fit_card failure mode (no network needed) ----------------------
def test_create_fit_card_empty_outfit():
    msg = create_fit_card("", {"title": "Faded Band Tee"})
    assert isinstance(msg, str) and len(msg) > 0   # error string, not an exception
