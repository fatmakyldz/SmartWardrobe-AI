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


def outfit_out(outfit: Outfit, items_by_id: dict[str, Item]) -> OutfitOut:
    # Items deleted since the suggestion are simply left out.
    items = [item_out(items_by_id[i]) for i in outfit.item_ids if i in items_by_id]
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
