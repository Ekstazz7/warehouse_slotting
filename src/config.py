"""
Конфігурація складського сектору, лімітів ваги, місткості та топологічних масок.
"""

DEFAULT_WEIGHT_BUFFER_KG = 25.0
VERTICAL_CLEARANCE_CM = 4.0

# Робоча вантажопідйомність полиць (кг)[cite: 4]
WEIGHT_LIMITS = {
    "deep_800": 275.0,        # Ряд 800 (001-005)[cite: 4]
    "deep_box": 115.0,        # Синя зона (ярус A)[cite: 4]
    "short_box": 45.0,        # Зелені короткі ящики (40 см)[cite: 4]
    "thin_slot": 45.0,        # Вузькі сині бокси 001-009[cite: 4]
    "continuous_300": 250.0   # Суцільні відкриті яруси B, C[cite: 4]
}

# Вантажопідйомність фіолетової зони (4 яруси)[cite: 4]
PURPLE_WEIGHT_LIMITS = {
    "001-005": 200.0,
    "A": 170.0,
    "B": 140.0,
    "C": 140.0
}

# Фізичні об'єми комірок (л) згідно з геометрією Паспорта[cite: 4]
SHELF_VOLUMES_L = {
    "deep_800": 336.0,        # 80 x 60 x 70 см[cite: 4]
    "continuous_300": 1056.0,  # 80 x 300 x 44 см[cite: 4]
    "thin_slot": 92.4,        # 40 x 33 x 70 см[cite: 4]
    "blue_a": 132.0,          # 40 x 60 x 55 см[cite: 4]
    "short_box": 132.0,       # 40 x 60 x 55 см[cite: 4]
    "purple_box": 264.0       # 80 x 60 x 55 см[cite: 4]
}

OVERSTOCK_THRESHOLDS = {
    "fast": 5,
    "slow": 3,
    "new": 1  # Для RN надлишок понад 5 шт. одразу спрямовується в overstock[cite: 4]
}

MAX_SKU_PER_STANDARD_BOX = 5
MAX_SKU_PER_SLOW_BOX = 9

ACCESS_WINDOW_BOX_CM = 55.0  # Чисте вікно доступу для стандартних боксів
ACCESS_CONTINUOUS_TIER_CM = 44.0 - VERTICAL_CLEARANCE_CM