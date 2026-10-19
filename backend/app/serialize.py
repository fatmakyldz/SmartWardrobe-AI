from .models import Item, Outfit
from .schemas import ItemOut, OutfitOut
from .storage import get_storage


def item_out(item: Item) -> ItemOut:
    return ItemOut(
        id=item.id,
        name=item.name,
        category=item.category,
        subcategory=item.subcategory,
        colors=item.colors or [],
        pattern=item.pattern,
        warmth=item.warmth,
        formality=item.formality,
        seasons=item.seasons or [],
        image_url=get_storage().url(item.image_key),
        created_at=item.created_at,
    )


def outfit_out(outfit: Outfit, items_by_id: dict[str, Item] | None = None) -> OutfitOut:
    # outfit_items (position order) is the source; deleted pieces are already gone from it (ON DELETE
    # CASCADE). item_ids is the fallback for rows written before 0002 that have no outfit_items.
    if outfit.outfit_items:
        items = [item_out(oi.item) for oi in sorted(outfit.outfit_items, key=lambda oi: oi.position)]
    else:
        items = [item_out(items_by_id[i]) for i in outfit.item_ids or [] if items_by_id and i in items_by_id]
    return OutfitOut(
        id=outfit.id,
        title=outfit.title,
        reason=outfit.reason,
        occasion=outfit.occasion,
        note=outfit.note,
        weather=outfit.weather or {},
        rating=outfit.rating,
        items=items,
        created_at=outfit.created_at,
    )
