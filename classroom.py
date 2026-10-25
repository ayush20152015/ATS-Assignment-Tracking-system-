"""Google Classroom integration: read submissions, set grades, return work.

TWO LIMITS YOU MUST KNOW (both come from Google's own documentation):
  1. Grades/returns can only be written by the SAME Cloud project that CREATED the
     coursework. Work created in the Classroom UI is therefore read-only to a
     standalone script -- that path needs a Classroom add-on with Grade Sync.
  2. Private comments are NOT exposed through the Classroom API.

So --live is best-effort. When it is refused, gradebot still writes the CSV + comment
files so you can apply them by hand. See README.md.
"""
from __future__ import annotations

import io
import os

import config


def get_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if os.path.exists(config.CLASSROOM_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(config.CLASSROOM_TOKEN_FILE,
                                                      config.CLASSROOM_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                config.CLASSROOM_CLIENT_SECRET, config.CLASSROOM_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(config.CLASSROOM_TOKEN_FILE, "w", encoding="utf-8") as fh:
            fh.write(creds.to_json())
    return creds


def get_service():
    from googleapiclient.discovery import build
    return build("classroom", "v1", credentials=get_credentials())


def get_drive_service():
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=get_credentials())


def list_submissions(service, course_id: str, coursework_id: str) -> list[dict]:
    subs: list[dict] = []
    token = None
    while True:
        resp = service.courses().courseWork().studentSubmissions().list(
            courseId=course_id, courseWorkId=coursework_id,
            pageToken=token, pageSize=100,
        ).execute()
        subs.extend(resp.get("studentSubmissions", []))
        token = resp.get("nextPageToken")
        if not token:
            break
    return subs


def student_name(service, user_id: str) -> str:
    try:
        prof = service.userProfiles().get(userId=user_id).execute()
        return prof.get("name", {}).get("fullName", user_id)
    except Exception:
        return user_id


def download_attachments(drive, submission: dict, out_dir: str, label: str) -> list[str]:
    """Download a submission's Drive attachments; returns the local file paths."""
    from googleapiclient.http import MediaIoBaseDownload

    os.makedirs(out_dir, exist_ok=True)
    paths: list[str] = []
    attachments = (submission.get("assignmentSubmission") or {}).get("attachments", []) or []
    for i, att in enumerate(attachments):
        df = att.get("driveFile")
        if not df:
            continue
        file_id = df.get("id")
        name = (df.get("title") or f"{label}_{i}")
        ext = os.path.splitext(name)[1] or ".bin"
        dest = os.path.join(out_dir, f"{label}_{i}{ext}")
        request = drive.files().get_media(fileId=file_id)
        with io.FileIO(dest, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        paths.append(dest)
    return paths


def push_grade_and_return(service, course_id: str, coursework_id: str,
                          submission_id: str, grade: float) -> tuple[bool, str]:
    """Set draftGrade + assignedGrade and return the submission. Best-effort."""
    from googleapiclient.errors import HttpError

    try:
        service.courses().courseWork().studentSubmissions().patch(
            courseId=course_id, courseWorkId=coursework_id, id=submission_id,
            updateMask="draftGrade,assignedGrade",
            body={"draftGrade": grade, "assignedGrade": grade},
        ).execute()
        sub = service.courses().courseWork().studentSubmissions()
        returner = getattr(sub, "return_", None) or getattr(sub, "classroomReturn")
        returner(courseId=course_id, courseWorkId=coursework_id, id=submission_id,
                 body={}).execute()
        return True, "graded and returned"
    except HttpError as e:
        code = getattr(e.resp, "status", "?")
        msg = e.content.decode("utf-8", "ignore") if hasattr(e, "content") else str(e)
        if code == 403 or "PERMISSION_DENIED" in msg:
            return False, ("PERMISSION_DENIED -- Google only lets the Cloud project that CREATED "
                           "this coursework write grades. Apply the CSV by hand, or build a "
                           "Classroom add-on with Grade Sync.")
        return False, f"HTTP {code}: {msg[:300]}"


def add_private_comment(drive, submission: dict, text: str) -> tuple[bool, str]:
    """Experimental: post the feedback as a Drive comment on the submission file.

    The Classroom API does not expose private comments, so we try the underlying
    Drive file. This works only for Drive-file attachments and may not appear in
    the Classroom UI. Treat it as best-effort.
    """
    from googleapiclient.errors import HttpError

    attachments = (submission.get("assignmentSubmission") or {}).get("attachments", []) or []
    file_id = None
    for att in attachments:
        if att.get("driveFile"):
            file_id = att["driveFile"].get("id")
            break
    if not file_id:
        return False, "no Drive attachment to comment on"
    try:
        drive.comments().create(fileId=file_id, body={"content": text},
                                fields="id").execute()
        return True, "comment posted"
    except HttpError as e:
        return False, f"Drive comment failed: {getattr(e.resp, 'status', '?')}"
