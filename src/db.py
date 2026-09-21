import math
import sqlite3
from pathlib import Path
import pandas as pd

from src.config import (
    ACCESS_CONTINUOUS_TIER_CM,
    PURPLE_WEIGHT_LIMITS,
    SHELF_VOLUMES_L,
    WEIGHT_LIMITS,
)
from src.models import ShelfType

# Автоматичне визначення кореня проєкту
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "warehouse_v2.db"
CSV_PATH = BASE_DIR / "data" / "suspension_arms.csv"


def get_connection(timeout: float = 60.0) -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=timeout)
    # WAL дозволяє читати з вікна Database і одночасно писати зі сканера:
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA busy_timeout = 60000;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    # executescript виконується без 'with conn:', оскільки сам відкриває та закриває транзакцію
    conn.executescript(
        """
        PRAGMA foreign_keys = OFF;
        DROP TABLE IF EXISTS inventory;
        DROP TABLE IF EXISTS overstock;
        DROP TABLE IF EXISTS shelves;
        DROP TABLE IF EXISTS sku_catalog;
        PRAGMA foreign_keys = ON;

        CREATE TABLE shelves (
            slot_id TEXT PRIMARY KEY,
            rack_id INTEGER NOT NULL,
            tier TEXT NOT NULL,
            box_number TEXT NOT NULL,
            shelf_type TEXT NOT NULL,
            max_weight_kg REAL NOT NULL,
            current_weight_kg REAL DEFAULT 0.0,
            max_volume_l REAL NOT NULL,
            current_volume_l REAL DEFAULT 0.0,
            entry_height_cm REAL NOT NULL,
            is_boxed_only INTEGER NOT NULL,
            is_blocked INTEGER NOT NULL,
            distance_cost REAL NOT NULL
        );

        CREATE TABLE sku_catalog (
            sku_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            pair_sku_id TEXT,
            side TEXT NOT NULL,
            arm_type TEXT NOT NULL,
            is_boxed INTEGER NOT NULL,
            length_cm REAL NOT NULL,
            width_cm REAL NOT NULL,
            height_cm REAL NOT NULL,
            weight_kg REAL NOT NULL,
            unit_volume_l REAL NOT NULL,
            effective_volume_l REAL NOT NULL,
            rotation TEXT NOT NULL,
            effective_rotation TEXT NOT NULL,
            sales_median_6m REAL NOT NULL,
            target_stock_qty INTEGER NOT NULL,
            batch_weight_kg REAL NOT NULL,
            batch_volume_l REAL NOT NULL
        );

        CREATE TABLE inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot_id TEXT NOT NULL,
            sku_id TEXT UNIQUE NOT NULL,
            quantity INTEGER NOT NULL,
            FOREIGN KEY (slot_id) REFERENCES shelves (slot_id),
            FOREIGN KEY (sku_id) REFERENCES sku_catalog (sku_id)
        );

        CREATE TABLE overstock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku_id TEXT UNIQUE NOT NULL,
            quantity INTEGER NOT NULL,
            total_weight_kg REAL NOT NULL,
            rotation TEXT NOT NULL,
            FOREIGN KEY (sku_id) REFERENCES sku_catalog (sku_id)
        );

        CREATE INDEX idx_shelves_type ON shelves (shelf_type);
        CREATE INDEX idx_shelves_blocked ON shelves (is_blocked);
        CREATE INDEX idx_sku_rotation ON sku_catalog (effective_rotation);
        """
    )


def calculate_distance_cost(rack_id: int, tier: str) -> float:
    row_num = rack_id // 100
    pos_num = rack_id % 100

    row_distance = abs(row_num - 7.5) * 4.0
    depth_distance = pos_num * 1.5
    ground_dist = math.sqrt(row_distance**2 + depth_distance**2)

    tier_penalties = {"A": 0.0, "001-005": 3.0, "001-009": 3.0, "B": 5.0, "C": 9.0}
    return round(ground_dist + tier_penalties.get(tier, 4.0), 2)


def generate_topology_shelves() -> list[dict]:
    slots = []

    # 1. Парний ряд 800 (800, 802 ... 820)
    for rack in range(800, 821, 2):
        dist_00 = calculate_distance_cost(rack, "001-005")
        for b in range(1, 6):
            slots.append({
                "slot_id": f"{rack}-00{b}",
                "rack_id": rack,
                "tier": "001-005",
                "box_number": f"00{b}",
                "shelf_type": ShelfType.DEEP_800.value,
                "max_weight_kg": WEIGHT_LIMITS["deep_800"],
                "max_volume_l": SHELF_VOLUMES_L["deep_800"],
                "entry_height_cm": 70.0,  # повна висота боксу
                "is_boxed_only": 0,
                "is_blocked": 0,
                "distance_cost": dist_00
            })

        if rack == 806:
            continue

        # Ярус А на 804 не використовується, на решті 800 — заблокований
        dist_a = calculate_distance_cost(rack, "A")
        for b in range(1, 6):
            slots.append({
                "slot_id": f"{rack}-A0{b}",
                "rack_id": rack,
                "tier": "A",
                "box_number": f"A0{b}",
                "shelf_type": ShelfType.DEEP_BOX.value,
                "max_weight_kg": 0.0,
                "max_volume_l": 0.0,
                "entry_height_cm": 55.0,
                "is_boxed_only": 0,
                "is_blocked": 1,
                "distance_cost": 999.0
            })

        if rack == 804:
            continue

        for tier in ["B", "C"]:
            slots.append({
                "slot_id": f"{rack}-{tier}00",
                "rack_id": rack,
                "tier": tier,
                "box_number": "300CM",
                "shelf_type": ShelfType.CONTINUOUS_300.value,
                "max_weight_kg": WEIGHT_LIMITS["continuous_300"],
                "max_volume_l": SHELF_VOLUMES_L["continuous_300"],
                "entry_height_cm": ACCESS_CONTINUOUS_TIER_CM,
                "is_boxed_only": 1,
                "is_blocked": 0,
                "distance_cost": calculate_distance_cost(rack, tier)
            })

    # 2. Синя зона (801-821 непарні та 700-720 парні)
    blue_racks = list(range(801, 822, 2)) + list(range(700, 721, 2))
    for rack in blue_racks:
        for b in range(1, 10):
            slots.append({
                "slot_id": f"{rack}-00{b}",
                "rack_id": rack,
                "tier": "001-009",
                "box_number": f"00{b}",
                "shelf_type": ShelfType.THIN_SLOT.value,
                "max_weight_kg": WEIGHT_LIMITS["thin_slot"],
                "max_volume_l": SHELF_VOLUMES_L["thin_slot"],
                "entry_height_cm": 70.0,
                "is_boxed_only": 0,
                "is_blocked": 0,
                "distance_cost": calculate_distance_cost(rack, "001-009")
            })

        for b in range(1, 6):
            slots.append({
                "slot_id": f"{rack}-A0{b}",
                "rack_id": rack,
                "tier": "A",
                "box_number": f"A0{b}",
                "shelf_type": ShelfType.DEEP_BOX.value,
                "max_weight_kg": WEIGHT_LIMITS["deep_box"],
                "max_volume_l": SHELF_VOLUMES_L["blue_a"],
                "entry_height_cm": 55.0,
                "is_boxed_only": 0,
                "is_blocked": 0,
                "distance_cost": calculate_distance_cost(rack, "A")
            })

        slots.append({
            "slot_id": f"{rack}-B00",
            "rack_id": rack,
            "tier": "B",
            "box_number": "300CM",
            "shelf_type": ShelfType.CONTINUOUS_300.value,
            "max_weight_kg": WEIGHT_LIMITS["continuous_300"],
            "max_volume_l": SHELF_VOLUMES_L["continuous_300"],
            "entry_height_cm": ACCESS_CONTINUOUS_TIER_CM,
            "is_boxed_only": 0,
            "is_blocked": 0,
            "distance_cost": calculate_distance_cost(rack, "B")
        })

        slots.append({
            "slot_id": f"{rack}-C00",
            "rack_id": rack,
            "tier": "C",
            "box_number": "300CM",
            "shelf_type": ShelfType.CONTINUOUS_300.value,
            "max_weight_kg": 0.0,
            "max_volume_l": 0.0,
            "entry_height_cm": ACCESS_CONTINUOUS_TIER_CM,
            "is_boxed_only": 0,
            "is_blocked": 1,
            "distance_cost": 999.0
        })

    # 3. Зелена зона (701-721, 600-620, 601-621, 500-520)
    green_racks = (
        list(range(701, 722, 2))
        + list(range(600, 621, 2))
        + list(range(601, 622, 2))
        + list(range(500, 521, 2))
    )
    for rack in green_racks:
        for tier in ["001-005", "A", "B"]:
            prefix = "" if tier == "001-005" else f"{tier}0"
            for b in range(1, 6):
                box_num = f"00{b}" if tier == "001-005" else f"{prefix}{b}"
                slots.append({
                    "slot_id": f"{rack}-{box_num}",
                    "rack_id": rack,
                    "tier": tier,
                    "box_number": box_num,
                    "shelf_type": ShelfType.SHORT_BOX.value,
                    "max_weight_kg": WEIGHT_LIMITS["short_box"],
                    "max_volume_l": SHELF_VOLUMES_L["short_box"],
                    "entry_height_cm": 55.0,
                    "is_boxed_only": 0,
                    "is_blocked": 0,
                    "distance_cost": calculate_distance_cost(rack, tier)
                })

        for b in range(1, 6):
            slots.append({
                "slot_id": f"{rack}-C0{b}",
                "rack_id": rack,
                "tier": "C",
                "box_number": f"C0{b}",
                "shelf_type": ShelfType.SHORT_BOX.value,
                "max_weight_kg": 0.0,
                "max_volume_l": 0.0,
                "entry_height_cm": 55.0,
                "is_boxed_only": 0,
                "is_blocked": 1,
                "distance_cost": 999.0
            })

    # 4. Фіолетова зона (501-521, 400-420, 401-419 без 421)
    purple_racks = (
        list(range(501, 522, 2))
        + list(range(400, 421, 2))
        + list(range(401, 420, 2))
    )
    for rack in purple_racks:
        for tier in ["001-005", "A", "B", "C"]:
            tier_max_w = PURPLE_WEIGHT_LIMITS[tier]
            prefix = "" if tier == "001-005" else f"{tier}0"
            dist_cost = calculate_distance_cost(rack, tier)

            for b in range(1, 6):
                box_num = f"00{b}" if tier == "001-005" else f"{prefix}{b}"
                slots.append({
                    "slot_id": f"{rack}-{box_num}",
                    "rack_id": rack,
                    "tier": tier,
                    "box_number": box_num,
                    "shelf_type": ShelfType.DEEP_BOX.value,
                    "max_weight_kg": tier_max_w,
                    "max_volume_l": SHELF_VOLUMES_L["purple_box"],
                    "entry_height_cm": 55.0,
                    "is_boxed_only": 0,
                    "is_blocked": 0,
                    "distance_cost": dist_cost
                })

    return slots


def setup_database():
    print("Ініціалізація структури БД...")
    conn = get_connection()
    try:
        init_schema(conn)
        print("Генерація топологічної карти...")
        shelves_data = generate_topology_shelves()
        pd.DataFrame(shelves_data).to_sql("shelves", conn, if_exists="append", index=False)

        if CSV_PATH.exists():
            df_sku = pd.read_csv(CSV_PATH)
            df_sku.to_sql("sku_catalog", conn, if_exists="append", index=False)
            print(f"Імпортовано {len(df_sku):,} SKU.")
        else:
            print("CSV-файл не знайдено, спочатку створіть каталог через generator.py")
    finally:
        conn.close()