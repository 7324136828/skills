#!/usr/bin/env python3
"""
Text-to-Speech (Kokoro)

Narrates a text file (e.g. the summary.txt produced by summarize_emails.py)
using the local Kokoro-82M TTS model and saves the result as an MP3.

Narrate summary.txt -> summary.mp3:
    python tts_kokoro.py
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# kokoro, numpy, pydub and imageio-ffmpeg are imported lazily so that --help and
# a missing-file error still work on a machine where they are not installed.

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_INPUT = Path("summary.txt")
DEFAULT_OUTPUT = Path("summary.mp3")

KOKORO_LANG_CODE = "a"      # American English
KOKORO_VOICE = "af_heart"
KOKORO_SAMPLE_RATE = 24000
MP3_BITRATE = "192k"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def remove_non_ascii(text: str) -> str:
    """Kokoro only handles ASCII text reliably; drop anything else."""
    return "".join(char for char in text if ord(char) < 128)


def require(package: str, pip_name: str):
    """Import a package, or exit with an actionable message."""
    try:
        return __import__(package)
    except ImportError:
        log.error(
            "The '%s' package is not installed. Install the audio dependencies "
            "with: python -m pip install -r requirements.txt   (or: python -m pip "
            "install %s)", package, pip_name,
        )
        sys.exit(1)


def synthesize_to_audio(text: str, lang_code: str, voice: str):
    np = require("numpy", "numpy")
    require("kokoro", "kokoro")
    from kokoro import KPipeline

    pipeline = KPipeline(lang_code=lang_code)
    generator = pipeline(text, voice=voice)
    chunks = [np.array(audio, dtype=np.float32) for _, _, audio in generator]
    if not chunks:
        raise RuntimeError("Kokoro produced no audio for the given text.")
    return np.concatenate(chunks)


def save_audio_as_mp3(audio, sample_rate: int, mp3_path: Path, bitrate: str = MP3_BITRATE) -> None:
    np = require("numpy", "numpy")
    require("pydub", "pydub")
    imageio_ffmpeg = require("imageio_ffmpeg", "imageio-ffmpeg")
    from pydub import AudioSegment

    AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()

    audio_int16 = (audio * 32767).astype(np.int16)
    segment = AudioSegment(
        audio_int16.tobytes(),
        frame_rate=sample_rate,
        sample_width=audio_int16.dtype.itemsize,
        channels=1,
    )
    segment.export(mp3_path, format="mp3", bitrate=bitrate)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Path to the text file to narrate.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Path to the output MP3 file.")
    parser.add_argument("--voice", default=KOKORO_VOICE, help="Kokoro voice name.")
    parser.add_argument("--lang-code", default=KOKORO_LANG_CODE, help="Kokoro language code (a=American English, b=British English, ...).")
    args = parser.parse_args()

    if not args.input.exists():
        log.error("Input text file '%s' not found. Run summarize_emails.py first.", args.input)
        sys.exit(1)

    text = remove_non_ascii(args.input.read_text(encoding="utf-8")).strip()
    if not text:
        log.warning("Input file '%s' is empty. Nothing to narrate.", args.input)
        sys.exit(0)

    log.info("Synthesizing speech with Kokoro (voice=%s)...", args.voice)
    try:
        audio = synthesize_to_audio(text, args.lang_code, args.voice)
    except Exception as exc:
        log.error("Speech synthesis failed: %s", exc)
        sys.exit(1)

    log.info("Saving MP3...")
    try:
        save_audio_as_mp3(audio, KOKORO_SAMPLE_RATE, args.output)
    except Exception as exc:
        log.error("MP3 conversion failed: %s", exc)
        sys.exit(1)

    log.info("Audio summary saved to %s", args.output)


if __name__ == "__main__":
    main()
