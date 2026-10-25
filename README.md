# gradebot

Grade Google Classroom assignments from a **spoken marking scheme**, and write a short
private-style comment explaining every deduction.

You dictate the rubric in Hindi / English / Hinglish. gradebot transcribes it, turns it into
a structured rubric, reads each student's handwritten submission (photos or PDFs), awards
marks criterion by criterion, and writes a comment for each student. It can also push the
grade back into Classroom.

```
voice clip  ──▶  transcript  ──▶  rubric (JSON)  ──▶  per-student grading  ──▶  CSV + comment
   (saaras)                       (sarvam-105b)        (gemma4 vision)          (+ Classroom API)
```

---

## 1. Quickstart (offline demo, no API key)

```bash
cd gradebot
python run.py --transcript samples/rubric_transcript.txt \
              --submissions samples/manifest.csv \
              --out out --brain mock
```

`--brain mock` runs the whole pipeline on the three sample submissions using a built-in
rubric, so you can see the outputs without any key. You get:

```
out/grading_report.csv     one row per student: score, deductions, feedback
out/grading_report.json    full per-criterion breakdown
out/comments/<student>.txt the private comment, ready to paste
```

## 2. For real

```bash
pip install -r requirements.txt
export SARVAM_API_KEY=sk_...           # https://dashboard.sarvam.ai

# spoken marking scheme in, grades out
python run.py --voice my_rubric.m4a --submissions ./submissions --out out --brain sarvam
```

`--submissions` is either a **folder** (each file is one student; the filename is the student
name) or a **CSV manifest** with columns `student,file`.

Useful flags:

| flag | meaning |
| --- | --- |
| `--voice a.m4a b.m4a` | one or more spoken clips (see the 30s note below) |
| `--transcript file.txt` | skip speech-to-text and use a transcript |
| `--voice-mode codemix` | keep Hinglish as-is (`transcribe` / `translate` / `verbatim` / `translit`) |
| `--max-marks 10` | total marks for the assignment |
| `--feedback-language hi` | write the student comment in Hindi |
| `--brain mock` | offline test mode |

## 3. Straight into Google Classroom (read this first)

```bash
python run.py --voice my_rubric.m4a --course-id 123456 --coursework-id 7890 --live
```

**Two limits will bite you, and they are Google's, not gradebot's:**

1. **Grades and returns can only be written by the same Google Cloud project that *created*
   the coursework.** Your Home Assignment 1 was created in the Classroom UI, so a standalone
   script with its own OAuth client will be refused (`PERMISSION_DENIED`). The supported route
   for third-party grading is a Classroom **add-on with Grade Sync** enabled — a much bigger
   build than this prototype.
2. **Private comments are not exposed by the Classroom API at all.**

So `--live` is written to do the right calls (`studentSubmissions.patch` to set
`draftGrade` + `assignedGrade`, then `studentSubmissions.return`), and it **degrades
gracefully**: if Google refuses, gradebot still writes the CSV and the per-student comment
files so you can apply them by hand in the Classroom UI. That is the realistic path today:
let gradebot do the reading and the writing, then paste the score and the comment.

`--push-comments` additionally tries an experimental path (a Drive comment on the submission
file). Treat it as best-effort — it may not surface in the Classroom UI.

To use `--live` you need a Google Cloud project with the Classroom + Drive APIs enabled and a
desktop OAuth client saved as `client_secret.json`. The first run opens a browser and caches a
`token.json`.

## 4. Layout

| file | job |
| --- | --- |
| `run.py` | CLI + orchestration |
| `stt.py` | speech-to-text (Sarvam `saaras`) |
| `brain.py` | rubric parsing + grading prompts (`sarvam-105b` text, `gemma4` vision) |
| `imaging.py` | photo/PDF → base64 JPEG pages for the vision model |
| `classroom.py` | OAuth, fetch submissions, push grade, return |
| `report.py` | CSV / JSON / comment files |
| `config.py` | env-var configuration |

Models are configurable: `GRADEBOT_STT_MODEL`, `GRADEBOT_VISION_MODEL`, `GRADEBOT_TEXT_MODEL`.

## 5. Known limits & next steps

- **Speech-to-text is capped at 30 seconds per clip** on the sync REST endpoint. gradebot
  joins several short clips and auto-splits long WAVs; for long m4a/mp3 recordings use Sarvam's
  **Batch API** (up to 2 hours) — a good next upgrade.
- **Handwritten maths is hard.** Expect the model to occasionally misread a step or a symbol.
  Always skim the CSV, especially rows flagged `confidence: medium/low` or with `notes`. Use
  this as a first pass, not a final authority.
- **`--live` push is untested against a real course** (it needs your OAuth setup and a
  project that owns the coursework). The offline pipeline is tested end to end.
- Nice next steps: a review UI before pushing, per-student point-in-time regrading when a
  student resubmits, and a class-wide statistics sheet.
