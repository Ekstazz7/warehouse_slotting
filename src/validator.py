"""
Валідація фізичних та логістичних обмежень для комірок.
"""

from typing import Set, Tuple
from src.config import MAX_SKU_PER_SLOW_BOX, MAX_SKU_PER_STANDARD_BOX
from src.models import ArmType, Rotation, ShelfSlot, ShelfType, SuspensionArmSKU

ROTATION_RANKS = {
    Rotation.R1: 1,
    Rotation.R2: 2,
    Rotation.R3: 3,
    Rotation.R4: 4,
    Rotation.R5: 5,
    Rotation.RN: 4,
}

SLOW_GROUP = {Rotation.R3, Rotation.R4, Rotation.R5, Rotation.RN}


def can_pass_entry_window(sku: SuspensionArmSKU, slot: ShelfSlot) -> bool:
    min_cross_dim = min(sku.height_cm, sku.width_cm)
    return min_cross_dim <= slot.entry_height_cm


def is_sku_limit_valid(sku: SuspensionArmSKU, slot: ShelfSlot, existing_skus: Set[str]) -> bool:
    if slot.shelf_type == ShelfType.CONTINUOUS_300:
        return True
    if sku.sku_id in existing_skus:
        return True
    if sku.effective_rotation in SLOW_GROUP:
        return len(existing_skus) < MAX_SKU_PER_SLOW_BOX
    return len(existing_skus) < MAX_SKU_PER_STANDARD_BOX


def is_rotation_compatible(sku: SuspensionArmSKU, existing_rotations: Set[Rotation]) -> bool:
    if not existing_rotations:
        return True
    if Rotation.R1 in existing_rotations or sku.effective_rotation == Rotation.R1:
        return False
    if sku.effective_rotation in SLOW_GROUP and existing_rotations.issubset(SLOW_GROUP):
        return True
    target_rank = ROTATION_RANKS.get(sku.effective_rotation, 4)
    for rot in existing_rotations:
        if abs(target_rank - ROTATION_RANKS.get(rot, 4)) > 1:
            return False
    return True


def validate_allocation(
    sku: SuspensionArmSKU,
    qty_to_place: int,
    slot: ShelfSlot,
    current_skus: Set[str],
    current_rotations: Set[Rotation],
) -> Tuple[bool, str]:
    if slot.is_blocked:
        return False, "Слот заблоковано"

    if slot.is_boxed_only and not sku.is_boxed:
        return False, "Лише коробки"

    if slot.shelf_type == ShelfType.THIN_SLOT:
        # У 001-009 дозволено прямі стійки (STRAIGHT_LINK) або дугові важелі (CURVED) <= 34 см
        is_thin_compatible = (sku.arm_type == ArmType.STRAIGHT_LINK) or (
            sku.arm_type == ArmType.CURVED and sku.length_cm <= 34.0
        )
        if not is_thin_compatible:
            return False, "У 001-009 дозволено лише стійки або короткі важелі <= 34 см"

    if not can_pass_entry_window(sku, slot):
        return False, "Габарити перевищують вікно доступу"

    added_weight = round(qty_to_place * sku.weight_kg, 2)
    if slot.current_weight_kg + added_weight > slot.max_weight_kg:
        return False, "Перевищення ліміту ваги"

    added_volume = round(qty_to_place * sku.effective_volume_l, 2)
    if slot.current_volume_l + added_volume > slot.max_volume_l:
        return False, "Перевищення ліміту кубатури полиці"

    if not is_sku_limit_valid(sku, slot, current_skus):
        return False, "Перевищено ліміт різновидів"

    if not is_rotation_compatible(sku, current_rotations):
        return False, "Несумісні ротації"

    return True, "OK"