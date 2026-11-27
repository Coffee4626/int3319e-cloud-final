"""Bounded CSV profiling and deterministic, reproducible data preparation.

No fitted imputers run here: AutoGluon fits feature transforms on its training split.
"""
import csv
import io
import math
import uuid
from collections import Counter

from app.domain import ConflictError, NotFoundError

MAX_BYTES = 10_000_000
MISSING = {"", "nan", "null", "none", "n/a"}


def missing(value):
    return value.strip().lower() in MISSING


def read_csv(text):
    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("CSV must be UTF-8 and at most 10 MB")
    try:
        reader = csv.reader(io.StringIO(text.lstrip("\ufeff")), strict=True)
        columns = next(reader, [])
        if not 2 <= len(columns) <= 200 or len(set(columns)) != len(columns) or any(not c.strip() or len(c) > 128 for c in columns):
            raise ValueError("CSV needs 2–200 unique, non-empty column headers")
        rows = []
        for row in reader:
            if not row:
                continue
            if len(row) != len(columns):
                raise ValueError(f"Row {len(rows) + 2} does not match header width")
            rows.append(row)
            if len(rows) > 100_000:
                raise ValueError("CSV limit: 100,000 rows")
    except csv.Error as exc:
        raise ValueError(f"Invalid CSV: {exc}") from exc
    if len(rows) < 2:
        raise ValueError("CSV needs at least two data rows")
    return columns, rows


def numeric(value):
    try:
        return math.isfinite(float(value))
    except (ValueError, OverflowError):
        return False


def profile(text):
    columns, rows = read_csv(text)
    result = []
    for i, name in enumerate(columns):
        values = [row[i] for row in rows if not missing(row[i])]
        is_numeric = bool(values) and all(numeric(v) for v in values)
        result.append({"name": name, "type": "numeric" if is_numeric else "categorical",
                       "missing": len(rows) - len(values), "unique": len(set(values)),
                       "examples": [v[:64] for v in list(dict.fromkeys(values))[:3]]})
    return {"rows": len(rows), "columns": result,
            "missing_cells": sum(c["missing"] for c in result),
            "duplicates": len(rows) - len({tuple(r) for r in rows}),
            "preview": [dict(zip(columns, [v[:64] for v in r])) for r in rows[:5]], "size_bytes": len(text.encode())}


def prepare(text, options):
    columns, rows = read_csv(text)
    target = options.get("target")
    if target not in columns:
        raise ValueError("Choose a target column")
    drops = options.get("drop_columns", [])
    if not isinstance(drops, list) or any(not isinstance(c, str) or c not in columns for c in drops):
        raise ValueError("drop_columns must contain existing column names")
    if target in drops or len(set(columns) - set(drops)) < 2:
        raise ValueError("Keep the target and at least one feature")
    for key in ("trim_strings", "drop_duplicates", "drop_missing_target"):
        if key in options and type(options[key]) is not bool:
            raise ValueError(f"{key} must be a boolean")
    keep = [i for i, c in enumerate(columns) if c not in drops]
    out_columns = [columns[i] for i in keep]
    target_index = out_columns.index(target)
    cleaned, seen, report = [], set(), Counter()
    for row in rows:
        row = [row[i].strip() if options.get("trim_strings", True) else row[i] for i in keep]
        row = ["" if missing(v) else v for v in row]
        if not row[target_index] and options.get("drop_missing_target", True):
            report["removed_missing_target"] += 1
            continue
        signature = tuple(row)
        if signature in seen and options.get("drop_duplicates", True):
            report["removed_duplicates"] += 1
            continue
        seen.add(signature)
        cleaned.append(row)
    if len(cleaned) < 2:
        raise ValueError("Preprocessing leaves fewer than two rows")
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(out_columns)
    writer.writerows(cleaned)
    return output.getvalue(), {**report, "input_rows": len(rows), "output_rows": len(cleaned),
                               "dropped_columns": drops}


class DatasetService:
    def __init__(self, repository, artifacts, owner="local"):
        self.repository, self.artifacts, self.owner = repository, artifacts, owner

    def get(self, dataset_id):
        item = self.repository.get_record(f"dataset#{dataset_id}")
        if not item or item.get("owner", "local") != self.owner:
            raise NotFoundError("Dataset not found")
        return item

    def create_upload(self, payload):
        name = payload.get("name", "dataset.csv")
        if not isinstance(name, str) or not name.strip() or len(name) > 200:
            raise ValueError("Dataset name must contain 1–200 characters")
        dataset_id = uuid.uuid4().hex
        key = f"uploads/{self.owner}/{dataset_id}.csv"
        self.repository.put_record({"id": f"dataset#{dataset_id}", "dataset_id": dataset_id,
                                   "name": name, "owner": self.owner, "kind": "dataset",
                                   "status": "UPLOADING", "upload_key": key})
        return {"dataset_id": dataset_id, "upload": self.artifacts.presign_upload(key, MAX_BYTES)}

    def complete(self, dataset_id):
        item = self.get(dataset_id)
        if item["status"] == "READY":
            return item
        text = self.artifacts.read_csv(item["upload_key"], MAX_BYTES)
        info = profile(text)
        # Snapshot the upload. A still-valid upload signature cannot mutate training data.
        key = f"datasets/{self.owner}/{dataset_id}/{uuid.uuid4().hex}.csv"
        self.artifacts.save_csv(key, text)
        item.update(status="READY", dataset_key=key, profile=info, prepared=False)
        self.repository.put_record(item)
        return item

    def preprocess(self, dataset_id, options):
        original = self.get(dataset_id)
        if original["status"] != "READY":
            raise ConflictError("Complete the upload first")
        text = self.artifacts.read_csv(original["dataset_key"], MAX_BYTES)
        cleaned, report = prepare(text, options)
        new_id = uuid.uuid4().hex
        key = f"datasets/{self.owner}/{new_id}.csv"
        self.artifacts.save_csv(key, cleaned)
        item = {"id": f"dataset#{new_id}", "dataset_id": new_id, "owner": self.owner,
                "kind": "dataset", "name": original["name"], "status": "READY",
                "source_id": dataset_id, "dataset_key": key, "prepared": True,
                "target": options["target"], "preprocessing": options,
                "report": report, "profile": profile(cleaned)}
        self.repository.put_record(item)
        return item
