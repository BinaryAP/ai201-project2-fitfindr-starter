"""
FitFindr — Gradio interface.

If your starter repo already has the Gradio layout wired, you only need the
handle_query() function below (the layout is at the bottom for completeness).
handle_query() calls run_agent() and maps the session dict onto the three
output panels: the listing found, the outfit suggestion, and the fit card.
"""

import gradio as gr
from agent import run_agent


def handle_query(query):
    """Run the agent and return three strings: (listing, outfit, fit_card)."""
    if not query or not query.strip():
        return ("Type a request to get started, e.g. "
                "\"vintage graphic tee under $30, size M\".", "", "")

    session = run_agent(query)

    # Error path: show the agent's informative message; leave other panels blank.
    if session.get("error"):
        return (f"⚠️ {session['error']}", "", "")

    item = session["selected_item"]
    listing_text = (
        f"**{item.get('title','(untitled)')}** — "
        f"${item.get('price','?')}, {item.get('platform','?')}, "
        f"{item.get('condition','?')} condition"
    )
    return (
        listing_text,
        session.get("outfit_suggestion") or "",
        session.get("fit_card") or "",
    )


# --- Layout (skip if your repo already provides it) ----------------------
with gr.Blocks(title="FitFindr") as demo:
    gr.Markdown("# 🧥 FitFindr\nFind secondhand pieces and figure out how to wear them.")
    query_in = gr.Textbox(
        label="What are you looking for?",
        placeholder="vintage graphic tee under $30, size M. I wear baggy jeans and chunky sneakers.",
    )
    go = gr.Button("Find a fit", variant="primary")
    listing_out = gr.Markdown(label="Listing found")
    outfit_out = gr.Textbox(label="Outfit suggestion", lines=3)
    card_out = gr.Textbox(label="Fit card", lines=2)

    go.click(handle_query, inputs=query_in, outputs=[listing_out, outfit_out, card_out])
    query_in.submit(handle_query, inputs=query_in, outputs=[listing_out, outfit_out, card_out])

if __name__ == "__main__":
    demo.launch()