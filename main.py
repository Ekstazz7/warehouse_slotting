"""
Головна точка входу Warehouse Slotting Engine.
Оркеструє етапи: генерація каталогу -> ініціалізація БД -> оптимізація розміщення -> експорт завдань для ТСД.
"""

import argparse
import sys
import time
from pathlib import Path

from src.allocator import WarehouseAllocator
from src.db import setup_database
from src.generator import generate_suspension_dataset
from src.tasks import TaskEngine


def run_full_pipeline(rebuild_data: bool = False):
    start_time = time.time()
    print("=" * 60)
    print("ЗАПУСК ПАЙПЛАЙНУ ОПТИМІЗАЦІЇ СКЛАДСЬКОГО СЕКТОРУ")
    print("=" * 60)

    # 1. Генерація каталогу
    csv_path = Path("data/suspension_arms.csv")
    if rebuild_data or not csv_path.exists():
        print("\n[КРОК 1/4] Генерація каталогу SKU...")
        df_sku = generate_suspension_dataset()
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        df_sku.to_csv(csv_path, index=False, encoding="utf-8")
        print(f"-> Каталог оновлено: {len(df_sku):,} SKU")
    else:
        print(f"\n[КРОК 1/4] Використання наявного каталогу: {csv_path}")

    # 2. Синхронізація топологічної карти
    print("\n[КРОК 2/4] Синхронізація топологічної карти сектору...")
    setup_database()

    # 3. Розподіл деталей
    print("\n[КРОК 3/4] Розрахунок оптимального розміщення...")
    allocator = WarehouseAllocator()
    allocator.allocate()
    allocator.save_results()
    allocator.print_summary()
    allocator.close()

    # 4. Формування завдань
    print("\n[КРОК 4/4] Формування пулу інструкцій для ТСД сканерів...")
    task_engine = TaskEngine()
    task_engine.generate_receipt_tasks()
    task_engine.export_tasks_json()
    task_engine.print_task_summary()
    task_engine.conn.close()

    elapsed = round(time.time() - start_time, 2)
    print(f"\n Пайплайн успішно виконано за {elapsed} сек.")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Warehouse Slotting Engine")
    parser.add_argument("--run-all", action="store_true")
    parser.add_argument("--rebuild-catalog", action="store_true")
    parser.add_argument("--tasks-only", action="store_true")

    args = parser.parse_args()

    if len(sys.argv) == 1 or args.run_all:
        run_full_pipeline(rebuild_data=args.rebuild_catalog)
    elif args.tasks_only:
        task_engine = TaskEngine()
        task_engine.generate_receipt_tasks()
        task_engine.export_tasks_json()
        task_engine.print_task_summary()
        task_engine.conn.close()


if __name__ == "__main__":
    main()