"""
Доменні моделі даних для деталей підвіски та комірок складу з урахуванням об'ємів.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Set, Tuple


class ArmType(str, Enum):
    STRAIGHT_LINK = "straight_link"    # Стійки стабілізатора, кермові наконечники
    TRAILING = "trailing"              # Поздовжні реактивні штанги
    CURVED = "curved"                  # Серпоподібні, дугові розвальні тяги
    A_SHAPED = "a_shaped"              # Трикутні важелі McPherson (Wishbone)
    HEAVY_INTEGRAL = "heavy_integral"  # Опорні важелі з чашкою під пружину


class Rotation(str, Enum):
    RN = "RN"  # Новий товар (ліміт <= 5 шт на полиці відбору)
    R1 = "R1"  # Топ-попит
    R2 = "R2"  # Стабільні
    R3 = "R3"  # Середні
    R4 = "R4"  # Повільні
    R5 = "R5"  # Неліквід


class ShelfType(str, Enum):
    SHORT_BOX = "short_box"            # Зелені бокси (40 см глибина)
    DEEP_BOX = "deep_box"              # Фіолетові (80 см) та Сині (40 см)
    THIN_SLOT = "thin_slot"            # Сині 001-009 (33 см ширина)
    DEEP_800 = "deep_800"              # Ряд 800 ярус 001-005 (80 см)
    CONTINUOUS_300 = "continuous_300"  # Відкриті суцільні полиці 300 см


ARM_VOLUME_COEFFICIENTS = {
    ArmType.STRAIGHT_LINK: 0.28,
    ArmType.TRAILING: 0.38,
    ArmType.CURVED: 0.42,
    ArmType.A_SHAPED: 0.52,
    ArmType.HEAVY_INTEGRAL: 0.68,
}


def calculate_part_volume(length_cm: float, width_cm: float, height_cm: float,
                          arm_type: ArmType, is_boxed: bool) -> Tuple[float, float]:
    """
    Рахує габаритний об'єм коробки та ефективний об'єм деталі в літрах.
    """
    raw_volume_l = round((length_cm * width_cm * height_cm) / 1000.0, 2)
    if is_boxed:
        effective_volume_l = round(raw_volume_l * 1.05, 2)
    else:
        coef = ARM_VOLUME_COEFFICIENTS.get(arm_type, 0.50)
        effective_volume_l = round(raw_volume_l * coef, 2)
    return raw_volume_l, max(0.1, effective_volume_l)


@dataclass
class SuspensionArmSKU:
    sku_id: str
    name: str
    pair_sku_id: Optional[str]
    side: str
    arm_type: ArmType
    is_boxed: bool
    length_cm: float
    width_cm: float
    height_cm: float
    weight_kg: float
    unit_volume_l: float
    effective_volume_l: float
    rotation: Rotation
    effective_rotation: Rotation
    sales_median_6m: float
    target_stock_qty: int
    batch_weight_kg: float
    batch_volume_l: float


@dataclass
class ShelfSlot:
    slot_id: str
    rack_id: int
    tier: str
    shelf_type: ShelfType
    max_weight_kg: float
    max_volume_l: float
    entry_height_cm: float
    is_boxed_only: bool
    is_blocked: bool
    allowed_rotations: Set[Rotation]
    current_weight_kg: float = 0.0
    current_volume_l: float = 0.0
    current_skus: Set[str] = None

    def __post_init__(self):
        if self.current_skus is None:
            self.current_skus = set()

    @property
    def free_weight_kg(self) -> float:
        return max(0.0, self.max_weight_kg - self.current_weight_kg)

    @property
    def free_volume_l(self) -> float:
        return max(0.0, self.max_volume_l - self.current_volume_l)