import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEMO_DIR = ROOT / "commercial" / "real_demo"
BUILD_DIR = DEMO_DIR / "build"
BUILD_DIR.mkdir(parents=True, exist_ok=True)
ITEMS = json.loads((DEMO_DIR / "narration_en.json").read_text(encoding="utf-8"))


def timestamp(seconds):
    milliseconds = int(round(seconds * 1000))
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


segments = []
subtitles = []
cursor = 0.0

for index, item in enumerate(ITEMS):
    stem = f"{index:02d}"
    text_file = BUILD_DIR / f"{stem}.txt"
    audio_file = BUILD_DIR / f"{stem}.aiff"
    segment_file = BUILD_DIR / f"{stem}.mp4"
    image_file = (DEMO_DIR / item["image"]).resolve()

    text_file.write_text(item["text"], encoding="utf-8")
    subprocess.run(
        ["say", "-v", "Daniel", "-r", "168", "-f", str(text_file), "-o", str(audio_file)],
        check=True,
    )
    audio_duration = float(
        subprocess.check_output(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(audio_file),
            ],
            text=True,
        ).strip()
    )
    duration = audio_duration + 1.0
    fade_out = max(0.0, duration - 0.4)

    subprocess.run(
        [
            "ffmpeg", "-y", "-loop", "1", "-i", str(image_file), "-i", str(audio_file),
            "-filter_complex",
            (
                "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
                "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=#111827,"
                f"fade=t=in:st=0:d=0.3,fade=t=out:st={fade_out}:d=0.3[v]"
            ),
            "-map", "[v]", "-map", "1:a", "-t", f"{duration:.3f}",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
            "-movflags", "+faststart", str(segment_file),
        ],
        check=True,
    )
    segments.append(segment_file)
    subtitles.append(
        f"{index + 1}\n{timestamp(cursor)} --> {timestamp(cursor + duration - 0.25)}\n"
        f"{item['text']}\n"
    )
    cursor += duration

concat_file = BUILD_DIR / "concat.txt"
concat_file.write_text(
    "\n".join(f"file '{path.as_posix()}'" for path in segments),
    encoding="utf-8",
)
subtitle_file = DEMO_DIR / "telegram_ai_hub_live_demo_en.srt"
subtitle_file.write_text("\n".join(subtitles), encoding="utf-8")
output_file = DEMO_DIR / "telegram_ai_hub_live_demo_en.mp4"

subprocess.run(
    [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-i", str(subtitle_file), "-map", "0:v", "-map", "0:a", "-map", "1:0",
        "-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text",
        "-metadata:s:s:0", "language=eng", "-metadata:s:s:0", "title=English",
        "-movflags", "+faststart", str(output_file),
    ],
    check=True,
)

print("LIVE_DEMO_READY", output_file, f"{cursor:.1f}s")
