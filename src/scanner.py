"""
Термінал Motorola WMS з меню в меню для реєстрації нових деталей
та автоматичним розрахунком кубатури за фізичним типом важеля.
"""

import sys
from typing import Optional, Tuple
from src.db import get_connection
from src.models import (
    ArmType,
    Rotation,
    ShelfType,
    calculate_part_volume,
)

TARGET_FILL_RATIO = 0.95


class MotorolaFinalScanner:
    def __init__(self):
        self.conn = get_connection()

    def lookup_sku(self, sku_id: str):
        return self.conn.execute(
            """
            SELECT sku_id, name, arm_type, is_boxed, length_cm, width_cm, 
                   height_cm, weight_kg, rotation, effective_volume_l
            FROM sku_catalog WHERE sku_id = ?
            """,
            (sku_id,),
        ).fetchone()

    def register_new_sku_interactive(self, sku_id: str) -> Optional[tuple]:
        print("\n" + "=" * 32, flush=True)
        print("  РЕЄСТРАЦІЯ НОВОГО ТОВАРУ", flush=True)
        print("=" * 32, flush=True)

        print("\n[МЕНЮ 1/3] Група вузла:", flush=True)
        print(" 1. Передня підвіска (Front)", flush=True)
        print(" 2. Задня підвіска (Rear)", flush=True)
        print(" 3. Рульове управління та стабілізатор", flush=True)
        group_choice = input("Виберіть групу [1-3]: ").strip()

        arm_type = ArmType.A_SHAPED
        if group_choice in ["1", "2"]:
            print("\n[МЕНЮ 2/3] Форм-фактор важеля:", flush=True)
            print(" 1. Трикутний McPherson / Wishbone (A-подібний)", flush=True)
            print(" 2. Серпоподібний / розвальна тяга (дуговий)", flush=True)
            print(" 3. Поздовжня реактивна тяга (довга штанга)", flush=True)
            print(" 4. Опорний важіль з чашкою під пружину", flush=True)
            sub = input("Виберіть тип [1-4]: ").strip()
            type_map = {
                "1": ArmType.A_SHAPED,
                "2": ArmType.CURVED,
                "3": ArmType.TRAILING,
                "4": ArmType.HEAVY_INTEGRAL
            }
            arm_type = type_map.get(sub, ArmType.A_SHAPED)
        else:
            print("\n[МЕНЮ 2/3] Рульове / лінки:", flush=True)
            print(" 1. Стійка стабілізатора (кісточка)", flush=True)
            print(" 2. Кермова тяга / наконечник", flush=True)
            sub = input("Виберіть тип [1-2]: ").strip()
            arm_type = ArmType.STRAIGHT_LINK

        print("\n[МЕНЮ 3/3] Сторона встановлення:", flush=True)
        print(" 1. Лівий (LH) | 2. Правий (RH) | 3. Симетричний (UNI)", flush=True)
        s_choice = input("Сторона [1-3]: ").strip()
        side = "LH" if s_choice == "1" else ("RH" if s_choice == "2" else "UNI")

        name = input("\nНазва деталі (Enter = Важіль): ").strip()
        if not name:
            name = f"Важіль {arm_type.value} {side}"

        boxed_in = input("У коробці? [1:Так / 0:Ні (голий метал)] (Enter = 0): ").strip()
        is_boxed = 1 if boxed_in == "1" else 0

        print("\nВведіть габарити деталі (см):", flush=True)
        l = float(input("  Довжина (см): ") or 35.0)
        w = float(input("  Ширина (см): ") or 15.0)
        h = float(input("  Висота (см): ") or 8.0)
        weight_kg = float(input("  Вага (кг): ") or 2.5)

        raw_vol, eff_vol = calculate_part_volume(l, w, h, arm_type, bool(is_boxed))
        print(f"\n>> Розрахунок: габаритний об'єм = {raw_vol} л | ефективний = {eff_vol} л", flush=True)

        print("\nРотація: [1:RN (Новий)] [2:R1] [3:R2] [4:R3] [5:R4] [6:R5]", flush=True)
        rot_choice = input("Оберіть [1-6] (Enter=1): ").strip()
        rot_map = {"1": "RN", "2": "R1", "3": "R2", "4": "R3", "5": "R4", "6": "R5"}
        rotation = rot_map.get(rot_choice, "RN")

        with self.conn:
            self.conn.execute(
                """
                INSERT INTO sku_catalog (
                    sku_id, name, pair_sku_id, side, arm_type, is_boxed,
                    length_cm, width_cm, height_cm, weight_kg,
                    unit_volume_l, effective_volume_l, rotation,
                    effective_rotation, sales_median_6m, target_stock_qty,
                    batch_weight_kg, batch_volume_l
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sku_id, name, None, side, arm_type.value, is_boxed,
                    l, w, h, weight_kg, raw_vol, eff_vol, rotation,
                    rotation, 0.0, 10, round(10 * weight_kg, 2), round(10 * eff_vol, 2)
                ),
            )
        print(f"Товар {sku_id} збережено!", flush=True)
        return self.lookup_sku(sku_id)

    def get_stock_info(self, sku_id: str, unit_weight: float, unit_vol: float) -> dict:
        inv_row = self.conn.execute(
            """
            SELECT i.slot_id, i.quantity, s.max_weight_kg, s.current_weight_kg,
                   s.max_volume_l, s.current_volume_l
            FROM inventory i
            JOIN shelves s ON i.slot_id = s.slot_id
            WHERE i.sku_id = ?
            """,
            (sku_id,),
        ).fetchone()

        over_row = self.conn.execute(
            "SELECT quantity FROM overstock WHERE sku_id = ?", (sku_id,)
        ).fetchone()
        over_qty = over_row[0] if over_row else 0

        if inv_row:
            slot_id, cur_qty, max_w, cur_w, max_v, cur_v = inv_row
            free_w = max(0.0, (max_w * TARGET_FILL_RATIO) - cur_w)
            free_v = max(0.0, (max_v * TARGET_FILL_RATIO) - cur_v)

            fit_by_w = int(free_w // unit_weight)
            fit_by_v = int(free_v // unit_vol) if unit_vol > 0 else 999
            fit_pcs = min(fit_by_w, fit_by_v)

            return {
                "is_assigned": True,
                "slot_id": slot_id,
                "shelf_qty": cur_qty,
                "fit_pcs": fit_pcs,
                "overstock_qty": over_qty,
            }

        return {
            "is_assigned": False,
            "slot_id": None,
            "shelf_qty": 0,
            "fit_pcs": 0,
            "overstock_qty": over_qty,
        }

    def find_shelf_for_new_sku(self, sku_data: tuple) -> Optional[Tuple[str, int]]:
        sku_id, name, arm_type, is_boxed, l, w, h, weight, rot_str, eff_vol = sku_data
        sku_rot = Rotation(rot_str)

        query = """
            SELECT slot_id, shelf_type, max_weight_kg, current_weight_kg, 
                   max_volume_l, current_volume_l, entry_height_cm, is_boxed_only
            FROM shelves
            WHERE is_blocked = 0 
              AND current_weight_kg < (max_weight_kg * 0.95)
              AND current_volume_l < (max_volume_l * 0.95)
            ORDER BY distance_cost ASC
        """
        slots = self.conn.execute(query).fetchall()

        for slot in slots:
            slot_id, shelf_type, max_w, cur_w, max_v, cur_v, entry_h, is_boxed_only = slot

            if bool(is_boxed) != bool(is_boxed_only):
                continue

            if shelf_type == ShelfType.THIN_SLOT.value:
                if not (arm_type == ArmType.STRAIGHT_LINK.value or l <= 34.0):
                    continue

            if shelf_type != ShelfType.CONTINUOUS_300.value and min(h, w) > entry_h:
                continue

            current_skus = {
                r[0] for r in self.conn.execute(
                    "SELECT sku_id FROM inventory WHERE slot_id = ?", (slot_id,)
                ).fetchall()
            }

            if sku_rot == Rotation.R1 and current_skus:
                continue

            free_w = (max_w * TARGET_FILL_RATIO) - cur_w
            free_v = (max_v * TARGET_FILL_RATIO) - cur_v
            fit_pcs = min(int(free_w // weight), int(free_v // eff_vol))
            if fit_pcs > 0:
                return (slot_id, fit_pcs)

        return None

    def commit_placement(
        self,
        slot_id: Optional[str],
        sku_id: str,
        shelf_qty: int,
        unit_weight: float,
        unit_vol: float,
        overstock_qty: int,
        rotation: str,
    ):
        with self.conn:
            if slot_id and shelf_qty > 0:
                added_w = round(shelf_qty * unit_weight, 2)
                added_v = round(shelf_qty * unit_vol, 2)

                existing = self.conn.execute(
                    "SELECT quantity FROM inventory WHERE sku_id = ?", (sku_id,)
                ).fetchone()

                if existing:
                    self.conn.execute(
                        "UPDATE inventory SET quantity = quantity + ?, slot_id = ? WHERE sku_id = ?",
                        (shelf_qty, slot_id, sku_id),
                    )
                else:
                    self.conn.execute(
                        "INSERT INTO inventory (slot_id, sku_id, quantity) VALUES (?, ?, ?)",
                        (slot_id, sku_id, shelf_qty),
                    )

                self.conn.execute(
                    """
                    UPDATE shelves 
                    SET current_weight_kg = current_weight_kg + ?, 
                        current_volume_l = current_volume_l + ? 
                    WHERE slot_id = ?
                    """,
                    (added_w, added_v, slot_id),
                )

            if overstock_qty > 0:
                over_w = round(overstock_qty * unit_weight, 2)
                self.conn.execute(
                    """
                    INSERT INTO overstock (sku_id, quantity, total_weight_kg, rotation)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(sku_id) DO UPDATE SET 
                        quantity = quantity + excluded.quantity,
                        total_weight_kg = total_weight_kg + excluded.total_weight_kg
                    """,
                    (sku_id, overstock_qty, over_w, rotation),
                )


def run_motorola_terminal():
    try:
        scanner = MotorolaFinalScanner()
    except Exception as e:
        print(f"ПОМИЛКА ПІДКЛЮЧЕННЯ ДО БД: {e}", flush=True)
        return

    print("================================", flush=True)
    print("      MOTOROLA WMS TERMINAL     ", flush=True)
    print("     КОНТРОЛЬ: ВАГА + КУБАТУРА  ", flush=True)
    print("================================", flush=True)

    while True:
        try:
            print("\n>> СКАНУВАННЯ SKU <<", flush=True)
            sku_input = input("ШТРИХКОД: ").strip().upper()
            if not sku_input or sku_input in ["EXIT", "QUIT"]:
                break

            sku_data = scanner.lookup_sku(sku_input)
            if not sku_data:
                sku_data = scanner.register_new_sku_interactive(sku_input)
                if not sku_data:
                    continue

            sku_id, name, arm_type, is_boxed, l, w, h, weight, rot, eff_vol = sku_data
            stock = scanner.get_stock_info(sku_id, weight, eff_vol)

            print("\n" + "=" * 32, flush=True)
            print(f" {sku_id} [{rot}]", flush=True)
            print(f" {name[:28]}", flush=True)
            print(f" Об'єм 1 шт: {eff_vol} л | Вага: {weight} кг", flush=True)
            print("-" * 32, flush=True)
            print(f" ПОЛИЦЯ [{stock['slot_id'] or 'НЕ ПРИЗНАЧЕНА'}]: {stock['shelf_qty']} шт.", flush=True)
            if stock["is_assigned"]:
                print(f" Вільне місце (вага+об'єм): {stock['fit_pcs']} шт.", flush=True)
            print(f" В НАДСТАНІ: {stock['overstock_qty']} шт.", flush=True)
            print("=" * 32, flush=True)

            qty_input = input("К-СТЬ НА РУКАХ (Enter = 1): ").strip()
            qty = int(qty_input) if qty_input.isdigit() and int(qty_input) > 0 else 1

            if stock["is_assigned"]:
                target_shelf = stock["slot_id"]
                fit_pcs = stock["fit_pcs"]
                if rot == "RN":
                    fit_pcs = min(fit_pcs, max(0, 5 - stock["shelf_qty"]))

                if fit_pcs <= 0:
                    over_pcs = qty
                    print("\n! МІСЦЕ ВИЧЕРПАНО -> У НАДСТАН !", flush=True)
                    scanner.commit_placement(None, sku_id, 0, weight, eff_vol, over_pcs, rot)
                    continue
                else:
                    shelf_pcs = min(qty, fit_pcs)
                    over_pcs = qty - shelf_pcs
            else:
                found = scanner.find_shelf_for_new_sku(sku_data)
                if found:
                    target_shelf, fit_pcs = found
                    if rot == "RN":
                        fit_pcs = min(fit_pcs, 5)
                    shelf_pcs = min(qty, fit_pcs)
                    over_pcs = qty - shelf_pcs
                else:
                    print("\n! НЕМАЄ ВІЛЬНИХ ПОЛИЦЬ -> У НАДСТАН !", flush=True)
                    scanner.commit_placement(None, sku_id, 0, weight, eff_vol, qty, rot)
                    continue

            if shelf_pcs > 0:
                print(f"\n>>> ПОЛИЦЯ ВІДБОРУ: [{target_shelf}] | ПОКЛАСТИ: {shelf_pcs} шт. <<<", flush=True)
                if over_pcs > 0:
                    print(f"Залишок у надстан: {over_pcs} шт.", flush=True)

                while True:
                    shelf_scan = input(f"СКАНУЙТЕ [{target_shelf}]: ").strip().upper()
                    if shelf_scan == target_shelf:
                        scanner.commit_placement(target_shelf, sku_id, shelf_pcs, weight, eff_vol, over_pcs, rot)
                        print("Підтверджено!", flush=True)
                        break
                    elif shelf_scan in ["SKIP", "CANCEL"]:
                        break
        except KeyboardInterrupt:
            break


if __name__ == "__main__":
    run_motorola_terminal()