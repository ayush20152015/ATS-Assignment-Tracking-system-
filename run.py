#!/usr/bin/env python3
"""gradebot -- grade Google Classroom assignments from a spoken marking scheme.

Offline demo (no API key needed):
    python run.py --transcript samples/rubric_transcript.txt \
                  --submissions samples/submissions --out out --brain mock

For real (Sarvam key required):
    export SARVAM_API_KEY=sk_...
    python run.py --voice rubric.m4a --submissions ./subs --out out --brain sarvam

Straight into Classroom (read the API caveat in README first):
    python run.py --voice rubric.m4a --course-id 123 --coursework-id 456 --live
"""
from __future__ import annotations

import argparse
import os
import sys

import brain
import config
import imaging
import report
import stt

# --------------------------------------------------------------------------- #
# Offline "mock" brain -- lets the whole pipeline be tested with no API key.
# --------------------------------------------------------------------------- #
MOCK_RUBRIC = {
    "title": "Home Assignment 1 - Two-port networks",
    "total_marks": 10,
    "criteria": [
        {"id": "c1", "description": "Find Z-parameters", "marks": 3, "guidance": "all four params"},
        {"id": "c2", "description": "Derive voltage transfer function V2/V1", "marks": 3,
         "guidance": "correct network equations"},
        {"id": "c3", "description": "State reciprocity & symmetry conditions", "marks": 2,
         "guidance": "both conditions"},
        {"id": "c4", "description": "Numerical example", "marks": 2, "guidance": "correct answer"},
    ],
    "penalties": [{"description": "missing units", "marks": 0.5}],
    "feedback_style": "short, encouraging, English",
    "extra_instructions": "explain every deduction",
    "assumptions": ["criterion marks split evenly when unclear"],
}


def mock_grade(student: str, images: list[str]) -> dict:
    seed = sum(ord(c) for c in student) % 5
    offsets = [0, -1.0, -0.5, -1.5, -2.0]
    score = 10 + offsets[seed]
    return {
        "student": student,
        "score": score,
        "max": 10,
        "criteria": [
            {"id": "c1", "awarded": 3, "max": 3, "comment": "All four Z-parameters correct."},
            {"id": "c2", "awarded": 2 if seed else 3, "max": 3,
             "comment": "Transfer function derived; one intermediate step skipped."},
            {"id": "c3", "awarded": 2, "max": 2, "comment": "Both conditions stated."},
            {"id": "c4", "awarded": 2 if seed < 3 else 1.5, "max": 2,
             "comment": "Numerical answer correct."},
        ],
        "deductions": ([] if seed == 0 else ["Skipped an intermediate step in the derivation."]) +
                      (["Missing units in the final answer."] if seed >= 3 else []),
        "feedback": (f"Hi {student.split()[0] if student else 'there'}, you scored {score}/10. "
                     "Good work on the Z-parameters and the reciprocity conditions. "
                     + ("One derivation step was skipped and units are missing at the end, "
                        "which cost you marks." if seed else "Everything was clean -- well done!"))
                     + " Please see the per-criterion notes.",
        "confidence": "high" if seed < 3 else "medium",
        "notes": "" if seed < 3 else "Photo is a bit dark; re-check the last step by eye.",
        "pages": len(images),
    }


# --------------------------------------------------------------------------- #
def discover_submissions(root: str) -> list[tuple[str, str]]:
    """Return [(student, path)] from a directory of files or a CSV manifest."""
    if root.lower().endswith(".csv"):
        import csv
        pairs: list[tuple[str, str]] = []
        with open(root, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                path = row["file"]
                if not os.path.isabs(path):
                    path = os.path.join(os.path.dirname(root), path)
                pairs.append((row.get("student", ""), path))
        return pairs
    exts = {".png", ".jpg", ".jpeg", ".webp", ".pdf"}
    pairs = []
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if os.path.isfile(path) and os.path.splitext(name)[1].lower() in exts:
            pairs.append((os.path.splitext(name)[0], path))
    return pairs


def main() -> int:
    ap = argparse.ArgumentParser(description="Grade Classroom assignments from a spoken rubric.")
    src = ap.add_argument_group("marking scheme")
    src.add_argument("--voice", nargs="+", metavar="AUDIO",
                     help="one or more spoken clips (Hindi/English) <=30s each")
    src.add_argument("--transcript", metavar="FILE", help="a ready transcript (skips speech-to-text)")
    src.add_argument("--voice-mode", default="transcribe",
                     choices=["transcribe", "translate", "codemix", "verbatim", "translit"],
                     help="speech-to-text output mode (default: transcribe)")
    src.add_argument("--language", default=None, help="language hint, e.g. hi-IN")

    g = ap.add_argument_group("grading")
    g.add_argument("--submissions", metavar="DIR_OR_CSV", help="folder of files, or a CSV manifest")
    g.add_argument("--max-marks", type=float, default=None, help="total marks for the assignment")
    g.add_argument("--brain", default="sarvam", choices=["sarvam", "mock"],
                   help="'mock' runs the whole pipeline offline for testing")
    g.add_argument("--feedback-language", default="en", help="en | hi | ... (default: en)")
    g.add_argument("--out", default="out", help="output folder (default: out)")

    c = ap.add_argument_group("google classroom (optional)")
    c.add_argument("--course-id", help="Classroom course id")
    c.add_argument("--coursework-id", help="Classroom courseWork id")
    c.add_argument("--live", action="store_true",
                   help="fetch from Classroom and push grades back (see README caveat)")
    c.add_argument("--push-comments", action="store_true",
                   help="also try the experimental Drive-comment path for feedback")

    args = ap.parse_args()

    # ---- 1. get the marking scheme as text ---------------------------------
    if args.transcript:
        with open(args.transcript, encoding="utf-8") as fh:
            transcript = fh.read()
        print(f"[1/4] marking scheme: read {len(transcript)} chars from {args.transcript}")
    elif args.voice:
        print(f"[1/4] transcribing {len(args.voice)} clip(s) with {config.STT_MODEL} ...")
        transcript = stt.transcribe(args.voice, mode=args.voice_mode,
                                    language_code=args.language, workdir=args.out)
        with open(os.path.join(args.out, "transcript.txt"), "w", encoding="utf-8") as fh:
            fh.write(transcript)
    else:
        ap.error("give either --voice AUDIO... or --transcript FILE")

    # ---- 2. structure the rubric -------------------------------------------
    if args.brain == "mock":
        rubric = MOCK_RUBRIC
        print("[2/4] rubric: using built-in MOCK rubric")
    else:
        print(f"[2/4] structuring rubric with {config.TEXT_MODEL} ...")
        rubric = brain.parse_rubric(transcript, args.max_marks)
    max_marks = args.max_marks or rubric.get("total_marks", 10)
    print(f"      {len(rubric.get('criteria', []))} criteria, total {max_marks} marks")
    for a in rubric.get("assumptions", []):
        print(f"      assumption: {a}")

    # ---- 3. gather + grade submissions -------------------------------------
    os.makedirs(args.out, exist_ok=True)
    results: list[dict] = []
    sub_by_id: dict[str, dict] = {}
    classroom_service = drive_service = None

    if args.live:
        if not (args.course_id and args.coursework_id):
            ap.error("--live needs --course-id and --coursework-id")
        import classroom
        classroom_service = classroom.get_service()
        drive_service = classroom.get_drive_service()
        subs = classroom.list_submissions(classroom_service, args.course_id, args.coursework_id)
        subs = [s for s in subs if s.get("state") == "TURNED_IN"]
        print(f"[3/4] Classroom: {len(subs)} submission(s) turned in")
        work = [(classroom.student_name(classroom_service, s["userId"]), s) for s in subs]
    else:
        if not args.submissions:
            ap.error("give --submissions DIR_OR_CSV (or use --live)")
        work = [(name, {"_path": path}) for name, path in discover_submissions(args.submissions)]
        print(f"[3/4] found {len(work)} submission(s) in {args.submissions}")

    for i, (student, sub) in enumerate(work, 1):
        if args.live:
            import classroom
            files = classroom.download_attachments(drive_service, sub,
                                                   os.path.join(args.out, "_downloads"),
                                                   f"{i:02d}_{student.replace(' ', '_')}")
            if not files:
                print(f"  [{i}/{len(work)}] {student}: no downloadable attachment -- skipped")
                continue
            pages: list[str] = []
            for f in files:
                pages.extend(imaging.load_submission(f))
            source = ", ".join(os.path.basename(f) for f in files)
        else:
            pages = imaging.load_submission(sub["_path"])
            source = sub["_path"]

        if args.brain == "mock":
            res = mock_grade(student, pages)
        else:
            res = brain.grade_submission(pages, rubric, rubric.get("extra_instructions", ""))
        res.setdefault("student", student)
        res.setdefault("max", max_marks)
        res["source"] = source
        if args.live:
            res["submission_id"] = sub["id"]
            sub_by_id[sub["id"]] = sub
        if args.feedback_language and args.feedback_language.lower() != "en" and args.brain != "mock":
            res["feedback"] = brain.rewrite_feedback(res.get("feedback", ""), args.feedback_language)
        results.append(res)
        print(f"  [{i}/{len(work)}] {student}: {res.get('score')}/{res.get('max')} "
              f"({res.get('confidence')})")

    # ---- 4. write + optionally push ----------------------------------------
    report.write_reports(results, args.out, max_marks)

    if args.live:
        import classroom
        print("[4/4] pushing to Classroom ...")
        ok = 0
        for r in results:
            sid = r.get("submission_id")
            if not sid:
                continue
            success, msg = classroom.push_grade_and_return(
                classroom_service, args.course_id, args.coursework_id, sid, float(r["score"]))
            print(f"  {r['student']}: {'OK' if success else 'SKIPPED'} -- {msg}")
            ok += int(success)
            if args.push_comments:
                c_ok, c_msg = classroom.add_private_comment(
                    drive_service, sub_by_id.get(sid, {}), r["feedback"])
                print(f"      comment: {'OK' if c_ok else 'skipped'} -- {c_msg}")
        print(f"      {ok}/{len(results)} graded via API; the rest are in the CSV for manual entry")
    else:
        print(f"[4/4] done. Grades + comments are in {args.out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
