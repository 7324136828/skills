#!/usr/bin/env python3
"""
Text-to-Speech (Windows SAPI)

Narrates a text file (e.g. the summary.txt produced by summarize_emails.py)
using the voices built into Windows (via .NET's System.Speech.Synthesis) and
saves the result as an MP3. No ML models or third-party TTS engines required
-- only pydub + imageio-ffmpeg (both pure-Python/no compiled extensions) for
the WAV -> MP3 conversion.

List available voices:
    python tts_sapi.py --list-voices

Narrate summary.txt -> summary.mp3:
    python tts_sapi.py
"""

import argparse
import logging
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_INPUT = Path("summary.txt")
DEFAULT_OUTPUT = Path("summary.mp3")
DEFAULT_VOICE = ""      # empty = Windows default voice
DEFAULT_RATE = 0        # SAPI rate, -10 (slowest) to 10 (fastest)

SPEAK_SCRIPT = """
param(
    [Parameter(Mandatory=$true)][string]$TextPath,
    [Parameter(Mandatory=$true)][string]$WavPath,
    [string]$VoiceName,
    [int]$Rate = 0
)
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
if ($VoiceName) {
    $synth.SelectVoice($VoiceName)
}
$synth.Rate = $Rate
$synth.SetOutputToWaveFile($WavPath)
$text = Get-Content -LiteralPath $TextPath -Raw -Encoding UTF8
$synth.Speak($text)
$synth.Dispose()
"""

LIST_VOICES_SCRIPT = """
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }
"""

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def run_powershell_script(script: str, args: list[str]) -> subprocess.CompletedProcess:
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as fh:
        fh.write(script)
        ps1_path = Path(fh.name)
    try:
        return subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps1_path), *args],
            check=True, capture_output=True, text=True,
        )
    finally:
        ps1_path.unlink(missing_ok=True)


def list_voices() -> list[str]:
    result = run_powershell_script(LIST_VOICES_SCRIPT, [])
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def synthesize_to_wav(text_path: Path, wav_path: Path, voice: str, rate: int) -> None:
    run_powershell_script(
        SPEAK_SCRIPT,
        ["-TextPath", str(text_path), "-WavPath", str(wav_path), "-VoiceName", voice, "-Rate", str(rate)],
    )


def convert_wav_to_mp3(wav_path: Path, mp3_path: Path) -> None:
    import imageio_ffmpeg
    from pydub import AudioSegment

    AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()
    segment = AudioSegment.from_file(wav_path, format="wav")
    segment.export(mp3_path, format="mp3")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Path to the text file to narrate.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Path to the output MP3 file.")
    parser.add_argument("--voice", default=DEFAULT_VOICE, help="Installed SAPI voice name (see --list-voices).")
    parser.add_argument("--rate", type=int, default=DEFAULT_RATE, help="Speaking rate, -10 (slowest) to 10 (fastest).")
    parser.add_argument("--list-voices", action="store_true", help="List installed voices and exit.")
    args = parser.parse_args()

    if args.list_voices:
        try:
            voices = list_voices()
        except subprocess.CalledProcessError as exc:
            log.error("Could not list voices: %s", exc.stderr)
            sys.exit(1)
        if not voices:
            log.warning("No installed voices found.")
        for name in voices:
            print(name)
        return

    if not args.input.exists():
        log.error("Input text file '%s' not found. Run summarize_emails.py first.", args.input)
        sys.exit(1)

    text = args.input.read_text(encoding="utf-8").strip()
    if not text:
        log.warning("Input file '%s' is empty. Nothing to narrate.", args.input)
        sys.exit(0)

    with tempfile.TemporaryDirectory() as tmp_dir:
        wav_path = Path(tmp_dir) / "speech.wav"

        log.info("Synthesizing speech (voice=%s, rate=%d)...", args.voice or "default", args.rate)
        try:
            synthesize_to_wav(args.input, wav_path, args.voice, args.rate)
        except subprocess.CalledProcessError as exc:
            log.error("Speech synthesis failed: %s", exc.stderr)
            sys.exit(1)

        log.info("Converting WAV to MP3...")
        try:
            convert_wav_to_mp3(wav_path, args.output)
        except Exception as exc:
            log.error("MP3 conversion failed: %s", exc)
            sys.exit(1)

    log.info("Audio summary saved to %s", args.output)


if __name__ == "__main__":
    main()
