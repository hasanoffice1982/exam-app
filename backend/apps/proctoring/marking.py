"""Combine a Google Forms responses export with proctoring results into a marks sheet.

Policy (kept simple and visible to teachers on the marks page):
- Quit the exam            -> 0 (the student was told this)
- Ended by a teacher       -> blank, decide manually
- No form submission found -> blank, decide manually
- Otherwise                -> the form's own score; flagged students get a "review first" note
- Form submissions from roll numbers with no attempt are listed as "submitted outside the app".
"""
import csv
import io
import re
from dataclasses import dataclass

from .models import ExamAttempt

MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_ROWS = 5000

ROLL_HINTS = ("roll", "registration", "reg no", "reg. no", "student id")
SCORE_HINTS = ("score", "marks", "grade")
TIME_HINTS = ("timestamp",)


class MarkingError(ValueError):
    """A problem with the uploaded file that the teacher can fix."""


@dataclass
class Responses:
    headers: list[str]
    rows: list[dict[str, str]]


def read_responses(raw: bytes) -> Responses:
    if len(raw) > MAX_UPLOAD_BYTES:
        raise MarkingError("File is too large (max 2 MB).")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise MarkingError("File must be UTF-8 CSV (export from Google Forms/Sheets as CSV).")
    reader = csv.DictReader(io.StringIO(text))
    headers = [h.strip() for h in (reader.fieldnames or [])]
    if not headers:
        raise MarkingError("The file has no header row.")
    rows = []
    for row in reader:
        if len(rows) >= MAX_ROWS:
            raise MarkingError(f"Too many rows (max {MAX_ROWS}).")
        rows.append({(k or "").strip(): (v or "").strip() for k, v in row.items()})
    return Responses(headers, rows)


def guess_column(headers: list[str], hints: tuple[str, ...]) -> str | None:
    for hint in hints:  # earlier hints win
        for header in headers:
            if hint in header.lower():
                return header
    return None


def parse_score(text: str) -> tuple[float | None, float | None]:
    """'8 / 10' -> (8, 10); '7.5' -> (7.5, None); '' or junk -> (None, None)."""
    match = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)\s*(?:/\s*(\d+(?:\.\d+)?))?\s*", text or "")
    if not match:
        return None, None
    return float(match.group(1)), float(match.group(2)) if match.group(2) else None


def normalise_roll(value: str) -> str:
    value = (value or "").strip().casefold()
    return value[:-2] if re.fullmatch(r"\d+\.0", value) else value  # spreadsheets turn 81 into 81.0


def _number(x: float | None):
    return None if x is None else (int(x) if x == int(x) else x)


def build_marks(live_rows: list[dict], responses: Responses, roll_column: str | None = None, score_column: str | None = None):
    """Returns (rows, outside_app, used_columns). `live_rows` come from dashboard.live_rows()."""
    roll_column = roll_column or guess_column(responses.headers, ROLL_HINTS)
    score_column = score_column or guess_column(responses.headers, SCORE_HINTS)
    time_column = guess_column(responses.headers, TIME_HINTS)
    for label, column in (("roll number", roll_column), ("score", score_column)):
        if column not in responses.headers:
            raise MarkingError(f"Could not find the {label} column. Columns in your file: {', '.join(responses.headers)}")

    by_roll: dict[str, list[dict[str, str]]] = {}
    for row in responses.rows:
        by_roll.setdefault(normalise_roll(row[roll_column]), []).append(row)

    def latest(rows: list[dict[str, str]]) -> dict[str, str]:
        return max(rows, key=lambda r: r.get(time_column, "")) if time_column and len(rows) > 1 else rows[-1]

    known = set()
    out = []
    for live in live_rows:
        key = normalise_roll(live["roll_number"])
        known.add(key)
        submissions = by_roll.get(key, [])
        score = maximum = mark = None
        notes = []
        if submissions:
            score, maximum = parse_score(latest(submissions)[score_column])
            if len(submissions) > 1:
                notes.append(f"{len(submissions)} submissions, latest used")
            if score is None:
                notes.append("score missing in form export")
        if live["status"] == ExamAttempt.Status.QUIT:
            mark, notes = 0, ["Quit the exam (marked 0)"] + notes
        elif live["status"] == ExamAttempt.Status.FORCE_ENDED:
            notes.insert(0, "Ended by teacher: decide manually")
        elif not submissions:
            notes.insert(0, "No form submission found")
        else:
            mark = score
        if live["flag"] == "flagged":
            notes.append(f"Flagged (proctor score {live['score']}): review before finalising")
        out.append(
            {
                "roll_number": live["roll_number"],
                "name": live["name"],
                "batch": live["batch"],
                "attempt_status": live["status_label"],
                "flag": live["flag"],
                "proctor_score": live["score"],
                "form_score": _number(score),
                "form_max": _number(maximum),
                "final_mark": _number(mark),
                "note": "; ".join(notes),
            }
        )
    outside = [
        {"roll": rows[-1][roll_column], "score": rows[-1][score_column], "submissions": len(rows)}
        for key, rows in by_roll.items()
        if key not in known and key
    ]
    return out, outside, {"roll": roll_column, "score": score_column}


MARK_COLUMNS = ["roll_number", "name", "batch", "attempt_status", "flag", "proctor_score", "form_score", "form_max", "final_mark", "note"]
