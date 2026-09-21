"""
Синтетичний генератор деталей підвіски з розрахунком об'ємів за новими типами.
"""

import math
import random
from dataclasses import asdict
from pathlib import Path
from typing import List, Tuple
import numpy as np
import pandas as pd

from src.models import ArmType, Rotation, SuspensionArmSKU, calculate_part_volume


def get_arm_geometry(arm_type: ArmType) -> Tuple[float, float, float, float]:
    if arm_type == ArmType.STRAIGHT_LINK:
        l, w, h = np.random.uniform(18.0, 32.0), np.random.uniform(4.0, 7.5), np.random.uniform(4.0, 7.5)
        weight = np.random.uniform(0.4, 1.4)
    elif arm_type == ArmType.CURVED:
        l, w, h = np.random.uniform(26.0, 42.0), np.random.uniform(10.0, 22.0), np.random.uniform(5.0, 11.0)
        weight = np.random.uniform(1.6, 3.4)
    elif arm_type == ArmType.A_SHAPED:
        l, w, h = np.random.uniform(36.0, 52.0), np.random.uniform(26.0, 42.0), np.random.uniform(7.0, 15.0)
        weight = np.random.uniform(3.6, 6.8)
    elif arm_type == ArmType.TRAILING:
        l, w, h = np.random.uniform(52.0, 78.0), np.random.uniform(6.0, 11.0), np.random.uniform(5.0, 9.0)
        weight = np.random.uniform(2.1, 4.2)
    else:  # HEAVY_INTEGRAL
        l, w, h = np.random.uniform(50.0, 82.0), np.random.uniform(16.0, 26.0), np.random.uniform(10.0, 18.0)
        weight = np.random.uniform(6.2, 10.5)

    return round(l, 1), round(w, 1), round(h, 1), round(weight, 2)


def generate_suspension_dataset(seed: int = 42) -> pd.DataFrame:
    np.random.seed(seed)
    random.seed(seed)
    records: List[SuspensionArmSKU] = []
    sku_counter = 1000

    # Оновлена конфігурація: 5 630 SKU (+1 500 нових позицій)
    config = [
        # (Ротація, парні комплекти, універсальні деталі, діапазон медіани продажів)
        (Rotation.R1, 170, 40, (30, 48)),  # 170*2 + 40  = 380 SKU (+70)
        (Rotation.R2, 440, 60, (18, 30)),  # 440*2 + 60  = 940 SKU (+220)
        (Rotation.R3, 720, 90, (8, 16)),  # 720*2 + 90  = 1 530 SKU (+360)
        (Rotation.R4, 880, 100, (3, 7)),  # 880*2 + 100 = 1 860 SKU (+480)
        (Rotation.R5, 200, 40, (1, 2)),  # 200*2 + 40  = 440 SKU (+180)
        (Rotation.RN, 200, 80, (0, 0)),  # 200*2 + 80  = 480 SKU (+190)
    ]

    for rot, n_pairs, n_uni, med_range in config:
        for _ in range(n_pairs):
            arm_type = random.choices(
                list(ArmType), weights=[0.25, 0.20, 0.25, 0.20, 0.10], k=1
            )[0]
            is_boxed = np.random.rand() < 0.08
            l, w, h, weight = get_arm_geometry(arm_type)
            raw_v, eff_v = calculate_part_volume(l, w, h, arm_type, is_boxed)

            if rot == Rotation.RN:
                l_med = r_med = 0.0
                l_qty = r_qty = int(np.random.randint(3, 6))
            else:
                base = np.random.uniform(*med_range)
                l_med = round(base * np.random.uniform(0.96, 1.04), 1)
                r_med = round(base * np.random.uniform(0.96, 1.04), 1)
                l_qty, r_qty = math.ceil(1.5 * l_med), math.ceil(1.5 * r_med)

            sku_l = f"SKU-{sku_counter}-LH"
            sku_r = f"SKU-{sku_counter}-RH"
            sku_counter += 1

            for s_code, p_code, side, med, qty in [
                (sku_l, sku_r, "LH", l_med, l_qty),
                (sku_r, sku_l, "RH", r_med, r_qty)
            ]:
                records.append(
                    SuspensionArmSKU(
                        sku_id=s_code,
                        name=f"Важіль {arm_type.value} {side} ({rot.value})",
                        pair_sku_id=p_code,
                        side=side,
                        arm_type=arm_type,
                        is_boxed=is_boxed,
                        length_cm=l,
                        width_cm=w,
                        height_cm=h,
                        weight_kg=weight,
                        unit_volume_l=raw_v,
                        effective_volume_l=eff_v,
                        rotation=rot,
                        effective_rotation=rot,
                        sales_median_6m=med,
                        target_stock_qty=qty,
                        batch_weight_kg=round(qty * weight, 1),
                        batch_volume_l=round(qty * eff_v, 1),
                    )
                )

        for _ in range(n_uni):
            arm_type = random.choices([ArmType.STRAIGHT_LINK, ArmType.TRAILING], weights=[0.8, 0.2], k=1)[0]
            is_boxed = np.random.rand() < 0.10
            l, w, h, weight = get_arm_geometry(arm_type)
            raw_v, eff_v = calculate_part_volume(l, w, h, arm_type, is_boxed)

            if rot == Rotation.RN:
                med_val, qty = 0.0, int(np.random.randint(2, 6))
            else:
                med_val = round(np.random.uniform(*med_range), 1)
                qty = math.ceil(1.5 * med_val)

            sku_uni = f"SKU-{sku_counter}-UNI"
            sku_counter += 1

            records.append(
                SuspensionArmSKU(
                    sku_id=sku_uni,
                    name=f"Тяга/стійка {arm_type.value} UNI ({rot.value})",
                    pair_sku_id=None,
                    side="UNI",
                    arm_type=arm_type,
                    is_boxed=is_boxed,
                    length_cm=l,
                    width_cm=w,
                    height_cm=h,
                    weight_kg=weight,
                    unit_volume_l=raw_v,
                    effective_volume_l=eff_v,
                    rotation=rot,
                    effective_rotation=rot,
                    sales_median_6m=med_val,
                    target_stock_qty=qty,
                    batch_weight_kg=round(qty * weight, 1),
                    batch_volume_l=round(qty * eff_v, 1),
                )
            )

    return pd.DataFrame([asdict(r) for r in records])


if __name__ == "__main__":
    out = Path("data")
    out.mkdir(parents=True, exist_ok=True)
    df = generate_suspension_dataset()
    df.to_csv(out / "suspension_arms.csv", index=False, encoding="utf-8")
    print(f"Каталог згенеровано: {len(df):,} SKU")