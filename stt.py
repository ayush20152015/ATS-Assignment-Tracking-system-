"""Turn the TA's spoken marking scheme into text.

The sync REST endpoint caps at 30 seconds per request, so we handle that by:
  * accepting several short clips and joining their transcripts in order, and
  * splitting a single long WAV file on the fly (WAV is the one format we can
    split with the standard library alone -- convert m4a/mp3 first if long).
"""
from __future__ import annotations

import os
import wave

import config
from sarvam_client import transcribe_file


def _wav_duration(path: str) -> float | None:
    try:
        with wave.open(path, "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return None


def _split_wav(path: str, seconds: int, workdir: str) -> list[str]:
    out: list[str] = []
    with wave.open(path, "rb") as w:
        params = w.getparams()
        frames_per_chunk = w.getframerate() * seconds
        idx = 0
        while True:
            frames = w.readframes(frames_per_chunk)
            if not frames:
                break
            chunk_path = os.path.join(workdir, f"_stt_chunk_{idx:03d}.wav")
            with wave.open(chunk_path, "wb") as c:
                c.setparams(params)
                c.writeframes(frames)
            out.append(chunk_path)
            idx += 1
    return out


def transcribe(paths: list[str], mode: str = "transcribe",
               language_code: str | None = None, workdir: str = ".",
               verbose: bool = True) -> str:
    """Transcribe one or more audio clips and return the joined text."""
    pieces: list[str] = []
    for path in paths:
        clips = [path]
        if path.lower().endswith(".wav"):
            dur = _wav_duration(path)
            if dur and dur > config.STT_MAX_SECONDS:
                clips = _split_wav(path, config.STT_MAX_SECONDS - 1, workdir)
                if verbose:
                    print(f"  split {os.path.basename(path)} ({dur:.0f}s) into {len(clips)} clips")
        for clip in clips:
            result = transcribe_file(clip, model=config.STT_MODEL, mode=mode,
                                     language_code=language_code)
            text = (result.get("transcript") or "").strip()
            if text:
                pieces.append(text)
            if verbose:
                print(f"  {os.path.basename(clip)} -> {len(text)} chars "
                      f"({result.get('language_code')})")
    return "\n".join(pieces)
