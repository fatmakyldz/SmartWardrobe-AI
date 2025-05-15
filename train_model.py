import os
import tensorflow as tf
from tensorflow.keras.preprocessing.image import ImageDataGenerator
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras import layers, models, Input, Model
from tensorflow.keras.callbacks import EarlyStopping

# ✅ Belleği temizle
tf.keras.backend.clear_session()

# 🔧 Ayarlar
DATA_DIR = "dataset_by_category"
IMG_SIZE = (224, 224)
BATCH_SIZE = 32
EPOCHS = 10

# ✅ Data Augmentation ve Setler
datagen = ImageDataGenerator(
    rescale=1./255,
    validation_split=0.2,
    horizontal_flip=True,
    zoom_range=0.2
)

train_generator = datagen.flow_from_directory(
    DATA_DIR,
    target_size=IMG_SIZE,
    batch_size=BATCH_SIZE,
    class_mode='categorical',
    subset='training',
    shuffle=True
)

val_generator = datagen.flow_from_directory(
    DATA_DIR,
    target_size=IMG_SIZE,
    batch_size=BATCH_SIZE,
    class_mode='categorical',
    subset='validation'
)

# ✅ Model (Functional API ile)
input_tensor = Input(shape=(*IMG_SIZE, 3))
base_model = MobileNetV2(weights='imagenet', include_top=False, input_tensor=input_tensor)
base_model.trainable = False

x = base_model.output
x = layers.GlobalAveragePooling2D()(x)
x = layers.Dense(128, activation='relu')(x)
x = layers.Dropout(0.3)(x)
output = layers.Dense(train_generator.num_classes, activation='softmax')(x)

model = Model(inputs=input_tensor, outputs=output)

model.compile(optimizer='adam', loss='categorical_crossentropy', metrics=['accuracy'])

# ✅ Eğitim
callbacks = [EarlyStopping(patience=3, restore_best_weights=True)]

history = model.fit(
    train_generator,
    validation_data=val_generator,
    epochs=EPOCHS,
    callbacks=callbacks
)

# ✅ Modeli kaydet
model.save("deepfashion_model.keras", save_format="keras")
print("✅ Model başarıyla kaydedildi!")
