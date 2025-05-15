import json

def load_location_data(path="data/turkiye.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def get_cities(data):
    return [il["il_adi"] for il in data]

def get_districts(data, selected_city):
    for il in data:
        if il["il_adi"] == selected_city:
            return [ilce["ilce_adi"] for ilce in il["ilceler"]]
    return []

def get_neighbourhoods(data, selected_city, selected_district):
    for il in data:
        if il["il_adi"] == selected_city:
            for ilce in il["ilceler"]:
                if ilce["ilce_adi"] == selected_district:
                    return [mah["mahalle_adi"] for mah in ilce["mahalleler"]]
    return []
