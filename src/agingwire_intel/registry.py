import csv
from pathlib import Path


def load_csv_registry(path: str | Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def source_registries(root: str | Path = "config/sources") -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(Path(root).glob("*.csv")):
        for row in load_csv_registry(path):
            row["_registry"] = path.name
            rows.append(row)
    return rows
