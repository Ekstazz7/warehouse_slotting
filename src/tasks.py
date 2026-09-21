"""
Генератор складських завдань для ТСД сканерів (Putaway & Overstock Routing).
Формує машиночитані черги операцій для інтеграції з WMS.
"""

import json
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd

from src.db import get_connection
from src.models import Rotation

TASKS_OUTPUT_PATH = Path("data/warehouse_tasks.json")


class TaskType(str, Enum):
    PUTAWAY_PICK_FACE = "PUTAWAY_PICK_FACE"      # Розміщення на робочу полицю відбору
    PUTAWAY_OVERSTOCK = "PUTAWAY_OVERSTOCK"      # Відправка залишку партії в надстан
    REPLENISHMENT = "REPLENISHMENT"              # Поповнення полиці з надстану


class TaskPriority(str, Enum):
    CRITICAL = "CRITICAL"  # R1 — блокує швидкі замовлення
    HIGH = "HIGH"          # R2
    MEDIUM = "MEDIUM"      # R3, RN
    LOW = "LOW"            # R4, R5


@dataclass
class WarehouseTask:
    task_id: str
    task_type: TaskType
    priority: TaskPriority
    sku_id: str
    sku_name: str
    source_location: str
    target_location: str
    quantity: int
    unit_weight_kg: float
    total_weight_kg: float
    rotation: str
    instruction: str


def get_task_priority(rotation: str) -> TaskPriority:
    """Визначає пріоритет виконання завдання для черги ТСД."""
    if rotation == Rotation.R1.value:
        return TaskPriority.CRITICAL
    if rotation == Rotation.R2.value:
        return TaskPriority.HIGH
    if rotation in [Rotation.R3.value, Rotation.RN.value]:
        return TaskPriority.MEDIUM
    return TaskPriority.LOW


class TaskEngine:
    def __init__(self):
        self.conn = get_connection()
        self.tasks: List[WarehouseTask] = []

    def generate_receipt_tasks(self, default_source: str = "RAMP-01") -> List[WarehouseTask]:
        """
        Генерує чергу завдань на розкладку на основі актуальних таблиць inventory та overstock.
        """
        self.tasks.clear()
        task_seq = 1

        # 1. Завдання на розміщення в робочі полиці відбору (Pick Face)
        query_inventory = """
            SELECT 
                i.sku_id,
                s.name,
                i.slot_id,
                i.quantity,
                s.weight_kg,
                s.rotation
            FROM inventory i
            JOIN sku_catalog s ON i.sku_id = s.sku_id
            ORDER BY 
                CASE s.effective_rotation
                    WHEN 'R1' THEN 1
                    WHEN 'R2' THEN 2
                    WHEN 'R3' THEN 3
                    WHEN 'RN' THEN 4
                    WHEN 'R4' THEN 5
                    WHEN 'R5' THEN 6
                END,
                i.slot_id ASC;
        """
        df_inv = pd.read_sql(query_inventory, self.conn)

        for _, row in df_inv.iterrows():
            total_w = round(row["quantity"] * row["weight_kg"], 2)
            rot = row["rotation"]
            self.tasks.append(
                WarehouseTask(
                    task_id=f"TSK-{task_seq:06d}",
                    task_type=TaskType.PUTAWAY_PICK_FACE,
                    priority=get_task_priority(rot),
                    sku_id=row["sku_id"],
                    sku_name=row["name"],
                    source_location=default_source,
                    target_location=row["slot_id"],
                    quantity=int(row["quantity"]),
                    unit_weight_kg=float(row["weight_kg"]),
                    total_weight_kg=total_w,
                    rotation=rot,
                    instruction=f"Розмістити {row['quantity']} шт. у робочу комірку {row['slot_id']}",
                )
            )
            task_seq += 1

        # 2. Завдання на переміщення надлишків у буфер надстанів (Overstock)
        query_overstock = """
            SELECT 
                o.sku_id,
                s.name,
                o.quantity,
                o.total_weight_kg,
                o.rotation,
                s.weight_kg
            FROM overstock o
            JOIN sku_catalog s ON o.sku_id = s.sku_id
            ORDER BY o.total_weight_kg DESC;
        """
        df_over = pd.read_sql(query_overstock, self.conn)

        for _, row in df_over.iterrows():
            rot = row["rotation"]
            self.tasks.append(
                WarehouseTask(
                    task_id=f"TSK-{task_seq:06d}",
                    task_type=TaskType.PUTAWAY_OVERSTOCK,
                    priority=get_task_priority(rot),
                    sku_id=row["sku_id"],
                    sku_name=row["name"],
                    source_location=default_source,
                    target_location="OVERSTOCK-BUFFER",
                    quantity=int(row["quantity"]),
                    unit_weight_kg=float(row["weight_kg"]),
                    total_weight_kg=float(row["total_weight_kg"]),
                    rotation=rot,
                    instruction=f"Спрямувати надлишок {row['quantity']} шт. у надстан (Overstock)",
                )
            )
            task_seq += 1

        return self.tasks

    def export_tasks_json(self, file_path: Path = TASKS_OUTPUT_PATH) -> None:
        """Експортує сформовані завдання у формат JSON для WMS."""
        data_to_export = [
            {
                **asdict(t),
                "task_type": t.task_type.value,
                "priority": t.priority.value,
            }
            for t in self.tasks
        ]
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data_to_export, f, ensure_ascii=False, indent=2)

    def print_task_summary(self) -> None:
        """Виводить звіт за типами та пріоритетами сформованих завдань."""
        total_tasks = len(self.tasks)
        pick_tasks = sum(1 for t in self.tasks if t.task_type == TaskType.PUTAWAY_PICK_FACE)
        over_tasks = sum(1 for t in self.tasks if t.task_type == TaskType.PUTAWAY_OVERSTOCK)

        print("\n" + "=" * 55)
        print("СЕРВІС ГЕНЕРАЦІЇ СКЛАДСЬКИХ ЗАВДАНЬ (WMS TASK DISPATCHER)")
        print("=" * 55)
        print(f"Всього сформовано інструкцій: {total_tasks:,}")
        print(f"  ├─ Завдання на полиці (Pick Face): {pick_tasks:,}")
        print(f"  └─ Завдання в надстан (Overstock): {over_tasks:,}")
        print(f"Експортовано у файл:             {TASKS_OUTPUT_PATH}")
        print("=" * 55)


if __name__ == "__main__":
    engine = TaskEngine()
    engine.generate_receipt_tasks()
    engine.export_tasks_json()
    engine.print_task_summary()