import os
import json

WARDROBE_FOLDER = "data"  # Veritabanı dosyalarının tutulduğu klasör

class WardrobeService:
    def __init__(self, username):
        self.username = username
        self.filepath = os.path.join(WARDROBE_FOLDER, f"wardrobe_{username}.json")
        self._ensure_file()

    def _ensure_file(self):
        # Eğer kullanıcıya ait gardırop dosyası yoksa, yeni bir dosya oluşturur
        if not os.path.exists(self.filepath):
            with open(self.filepath, "w") as f:
                json.dump([], f)  # Başlangıçta boş bir liste ile başlatıyoruz

    def load_wardrobe(self):
        # Gardıroptaki kıyafetleri yükler
        with open(self.filepath, "r") as f:
            return json.load(f)

    def save_wardrobe(self, wardrobe):
        # Kıyafetleri JSON dosyasına kaydeder
        with open(self.filepath, "w") as f:
            json.dump(wardrobe, f, indent=4)

    def add_item(self, item):
        # Yeni bir kıyafet ekler
        wardrobe = self.load_wardrobe()
        wardrobe.append(item)
        self.save_wardrobe(wardrobe)  # JSON dosyasına kaydeder
def load_filtered_wardrobe(event, temperature, wardrobe_path="data/wardrobe_fatma.json"):
    with open(wardrobe_path, "r") as f:
        items = json.load(f)

    # Sıcaklığa göre hava etiketi seç
    if temperature >= 26:
        weather_tag = "Hot"
    elif temperature >= 15:
        weather_tag = "Mild"
    else:
        weather_tag = "Cold"

    filtered = []
    for item in items:
        if (
            event in item.get("event_tags", []) and
            weather_tag in item.get("weather_tags", [])
        ):
            filtered.append(item)

    return filtered