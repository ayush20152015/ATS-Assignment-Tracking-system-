"""Write the grading results to disk: a CSV, a JSON, and one comment file per student."""
from __future__ import annotations

import csv
import json
import os


def _safe(name: str) -> str:
    keep = "".join(c if (c.isalnum() or c in "-_ ") else "_" for c in (name or "student"))
    return keep.strip() or "student"


def write_reports(results: list[dict], out_dir: str, max_marks: float) -> None:
    os.makedirs(out_dir, exist_ok=True)

    with open(os.path.join(out_dir, "grading_report.json"), "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)

    with open(os.path.join(out_dir, "grading_report.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["student", "score", "max", "confidence", "deductions",
                    "feedback", "notes", "submission_id", "source"])
        for r in results:
            criteria = "; ".join(
                f"{c.get('id')}: {c.get('awarded')}/{c.get('max')}" for c in r.get("criteria", [])
            )
            w.writerow([
                r.get("student", ""), r.get("score", ""), r.get("max", max_marks),
                r.get("confidence", ""), " | ".join(r.get("deductions", [])),
                r.get("feedback", ""), r.get("notes", ""),
                r.get("submission_id", ""), r.get("source", ""),
            ])
            if criteria:
                w.writerow(["", "", "", "", f"criteria: {criteria}", "", "", "", ""])

    comments_dir = os.path.join(out_dir, "comments")
    os.makedirs(comments_dir, exist_ok=True)
    for r in results:
        label = _safe(r.get("student") or r.get("submission_id"))
        with open(os.path.join(comments_dir, f"{label}.txt"), "w", encoding="utf-8") as fh:
            fh.write(r.get("feedback", ""))

    print(f"  wrote {len(results)} results to {out_dir}/ "
          f"(grading_report.csv, grading_report.json, comments/)")
