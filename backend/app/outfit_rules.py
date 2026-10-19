"""What makes a valid outfit. Shared by AI suggestions (ai.features.suggest) and user outfits (services)."""


def complete_outfit(categories) -> bool:
    cats = set(categories)
    return "dress" in cats or {"top", "bottom"} <= cats


def valid_item_set(items) -> bool:
    """Objects with .id and .category: no repeats, one per category (accessories aside), complete."""
    seen, cats = set(), []
    for i in items:
        if i.id in seen or (i.category in cats and i.category != "accessory"):
            return False
        seen.add(i.id)
        cats.append(i.category)
    return complete_outfit(cats)
