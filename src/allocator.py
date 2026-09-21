"""
Двигун алокації: розкладання за подвійним фактором (вага + об'єм до 80%).
"""

from dataclasses import dataclass
from typing import Dict, List, Set
import pandas as pd

from src.config import OVERSTOCK_THRESHOLDS
from src.db import get_connection
from src.models import ArmType, Rotation, ShelfSlot, ShelfType, SuspensionArmSKU
from src.validator import validate_allocation

TARGET_FILL_RATIO = 0.80


@dataclass
class AllocationRecord:
    slot_id: str
    sku_id: str
    quantity: int
    total_weight_kg: float
    total_volume_l: float


@dataclass
class OverstockRecord:
    sku_id: str
    quantity: int
    total_weight_kg: float
    rotation: str


class WarehouseAllocator:
    def __init__(self):
        self.conn = get_connection()
        self.shelves: Dict[str, ShelfSlot] = {}
        self.shelf_skus: Dict[str, Set[str]] = {}
        self.shelf_rotations: Dict[str, Set[Rotation]] = {}
        self.allocations: List[AllocationRecord] = []
        self.overstock_list: List[OverstockRecord] = []

    def load_state(self) -> List[SuspensionArmSKU]:
        df_shelves = pd.read_sql(
            """
            SELECT slot_id, rack_id, tier, shelf_type, max_weight_kg, 
                   current_weight_kg, max_volume_l, current_volume_l, 
                   entry_height_cm, is_boxed_only, is_blocked, distance_cost 
            FROM shelves 
            WHERE is_blocked = 0 
            ORDER BY distance_cost ASC
            """,
            self.conn,
        )

        for _, r in df_shelves.iterrows():
            slot = ShelfSlot(
                slot_id=r["slot_id"],
                rack_id=int(r["rack_id"]),
                tier=r["tier"],
                shelf_type=ShelfType(r["shelf_type"]),
                max_weight_kg=float(r["max_weight_kg"]),
                max_volume_l=float(r["max_volume_l"]),
                entry_height_cm=float(r["entry_height_cm"]),
                is_boxed_only=bool(r["is_boxed_only"]),
                is_blocked=bool(r["is_blocked"]),
                allowed_rotations=set(),
            )
            self.shelves[slot.slot_id] = slot
            self.shelf_skus[slot.slot_id] = set()
            self.shelf_rotations[slot.slot_id] = set()

        df_sku = pd.read_sql(
            """
            SELECT * FROM sku_catalog 
            ORDER BY 
                CASE effective_rotation 
                    WHEN 'R1' THEN 1 
                    WHEN 'R2' THEN 2 
                    WHEN 'R3' THEN 3 
                    WHEN 'RN' THEN 4 
                    WHEN 'R4' THEN 5 
                    WHEN 'R5' THEN 6 
                END ASC,
                batch_weight_kg DESC
            """,
            self.conn,
        )

        skus = []
        for _, r in df_sku.iterrows():
            skus.append(
                SuspensionArmSKU(
                    sku_id=r["sku_id"],
                    name=r["name"],
                    pair_sku_id=r["pair_sku_id"],
                    side=r["side"],
                    arm_type=ArmType(r["arm_type"]),
                    is_boxed=bool(r["is_boxed"]),
                    length_cm=float(r["length_cm"]),
                    width_cm=float(r["width_cm"]),
                    height_cm=float(r["height_cm"]),
                    weight_kg=float(r["weight_kg"]),
                    unit_volume_l=float(r["unit_volume_l"]),
                    effective_volume_l=float(r["effective_volume_l"]),
                    rotation=Rotation(r["rotation"]),
                    effective_rotation=Rotation(r["effective_rotation"]),
                    sales_median_6m=float(r["sales_median_6m"]),
                    target_stock_qty=int(r["target_stock_qty"]),
                    batch_weight_kg=float(r["batch_weight_kg"]),
                    batch_volume_l=float(r["batch_volume_l"]),
                )
            )
        return skus

    def allocate(self):
        skus = self.load_state()
        all_slots = list(self.shelves.values())

        for sku in skus:
            is_thin_compatible = (
                sku.arm_type == ArmType.STRAIGHT_LINK or
                (sku.arm_type == ArmType.CURVED and sku.length_cm <= 34.0)
            )

            if is_thin_compatible:
                candidate_slots = [s for s in all_slots if s.shelf_type == ShelfType.THIN_SLOT] + [s for s in all_slots if s.shelf_type != ShelfType.THIN_SLOT]
            elif sku.effective_rotation == Rotation.R1:
                candidate_slots = [s for s in all_slots if s.current_weight_kg == 0 and s.shelf_type in [ShelfType.DEEP_800, ShelfType.CONTINUOUS_300, ShelfType.DEEP_BOX]] + all_slots
            else:
                candidate_slots = all_slots

            best_slot_id = None
            placed_qty = 0

            for slot in candidate_slots:
                slot_id = slot.slot_id
                free_w = max(0.0, (slot.max_weight_kg * TARGET_FILL_RATIO) - slot.current_weight_kg)
                free_v = max(0.0, (slot.max_volume_l * TARGET_FILL_RATIO) - slot.current_volume_l)

                if free_w < sku.weight_kg or free_v < sku.effective_volume_l:
                    continue

                by_w = int(free_w // sku.weight_kg)
                by_v = int(free_v // sku.effective_volume_l) if sku.effective_volume_l > 0 else 999
                test_qty = min(sku.target_stock_qty, by_w, by_v)

                if sku.rotation == Rotation.RN or sku.effective_rotation == Rotation.RN:
                    test_qty = min(test_qty, 5)

                if test_qty <= 0:
                    continue

                is_valid, _ = validate_allocation(
                    sku, test_qty, slot, self.shelf_skus[slot_id], self.shelf_rotations[slot_id]
                )
                if is_valid:
                    best_slot_id = slot_id
                    placed_qty = test_qty
                    break

            if best_slot_id:
                slot = self.shelves[best_slot_id]
                added_w = round(placed_qty * sku.weight_kg, 2)
                added_v = round(placed_qty * sku.effective_volume_l, 2)

                slot.current_weight_kg += added_w
                slot.current_volume_l += added_v
                self.shelf_skus[best_slot_id].add(sku.sku_id)
                self.shelf_rotations[best_slot_id].add(sku.effective_rotation)

                self.allocations.append(
                    AllocationRecord(best_slot_id, sku.sku_id, placed_qty, added_w, added_v)
                )

                excess_qty = sku.target_stock_qty - placed_qty
                if excess_qty > 0:
                    is_rn = (sku.rotation == Rotation.RN or sku.effective_rotation == Rotation.RN)
                    threshold = OVERSTOCK_THRESHOLDS["new"] if is_rn else OVERSTOCK_THRESHOLDS["slow"]
                    if excess_qty >= threshold:
                        self.overstock_list.append(
                            OverstockRecord(
                                sku.sku_id, excess_qty, round(excess_qty * sku.weight_kg, 2), sku.rotation.value
                            )
                        )
            else:
                self.overstock_list.append(
                    OverstockRecord(
                        sku.sku_id, sku.target_stock_qty, round(sku.target_stock_qty * sku.weight_kg, 2), sku.rotation.value
                    )
                )

    def save_results(self):
        with self.conn:
            self.conn.execute("DELETE FROM inventory;")
            self.conn.execute("DELETE FROM overstock;")
            self.conn.executemany(
                "INSERT INTO inventory (slot_id, sku_id, quantity) VALUES (?, ?, ?)",
                [(a.slot_id, a.sku_id, a.quantity) for a in self.allocations],
            )
            self.conn.executemany(
                "INSERT INTO overstock (sku_id, quantity, total_weight_kg, rotation) VALUES (?, ?, ?, ?)",
                [(o.sku_id, o.quantity, o.total_weight_kg, o.rotation) for o in self.overstock_list],
            )
            for s in self.shelves.values():
                self.conn.execute(
                    "UPDATE shelves SET current_weight_kg = ?, current_volume_l = ? WHERE slot_id = ?",
                    (round(s.current_weight_kg, 2), round(s.current_volume_l, 2), s.slot_id),
                )

    def close(self):
        if self.conn:
            self.conn.close()

    def print_summary(self):
        total_target_pcs = sum(r[0] for r in self.conn.execute("SELECT SUM(target_stock_qty) FROM sku_catalog").fetchall())
        placed_pcs = sum(a.quantity for a in self.allocations)
        overstock_pcs = sum(o.quantity for o in self.overstock_list)
        occupied_shelves = sum(1 for s in self.shelves.values() if s.current_weight_kg > 0)

        ratios_w = [s.current_weight_kg / s.max_weight_kg for s in self.shelves.values() if s.current_weight_kg > 0]
        ratios_v = [s.current_volume_l / s.max_volume_l for s in self.shelves.values() if s.max_volume_l > 0 and s.current_volume_l > 0]

        avg_w = (sum(ratios_w) / len(ratios_w)) * 100 if ratios_w else 0.0
        avg_v = (sum(ratios_v) / len(ratios_v)) * 100 if ratios_v else 0.0

        print("\n" + "=" * 55)
        print("РЕЗУЛЬТАТИ 2-ФАКТОРНОЇ АЛОКАЦІЇ (ВАГА + КУБАТУРА)")
        print("=" * 55)
        print(f"Цільовий пул каталогу:         {total_target_pcs:,} шт.")
        print(f"Розміщено на полицях сектору:  {placed_pcs:,} шт. ({round(placed_pcs/total_target_pcs*100, 1)}%)")
        print(f"Буфер надстанів:               {overstock_pcs:,} шт. ({round(overstock_pcs/total_target_pcs*100, 1)}%)")
        print(f"Задіяно полиць сектору:        {occupied_shelves} із {len(self.shelves)} активних")
        print(f"Середнє завантаження за вагою: {round(avg_w, 1)}% (ліміт 80%)")
        print(f"Середнє заповнення за кубатурою:{round(avg_v, 1)}% (ліміт 80%)")
        print("=" * 55)