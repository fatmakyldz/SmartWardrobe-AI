import os
import pandas as pd
import shutil

# === AYARLAR ===
source_folder = "dataset/images"
csv_path = "dataset/styles.csv"
output_folder = "dataset_by_category"

# CSV'yi oku
df = pd.read_csv(csv_path, on_bad_lines='skip')
df['id'] = df['id'].astype(str)
df = df.dropna(subset=['subCategory'])

# Görselleri klasörlere kopyala
for _, row in df.iterrows():
    img_id = row['id']
    category = row['subCategory'].strip().replace('/', '-')
    img_filename = f"{img_id}.jpg"

    src_path = os.path.join(source_folder, img_filename)
    dest_dir = os.path.join(output_folder, category)

    os.makedirs(dest_dir, exist_ok=True)

    if os.path.exists(src_path):
        shutil.copy2(src_path, os.path.join(dest_dir, img_filename))

print("✅ Görseller başarıyla kategorilere ayrıldı!")
