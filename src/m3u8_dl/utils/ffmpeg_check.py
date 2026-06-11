import shutil
import subprocess


def check_ffmpeg() -> str | None:
    path = shutil.which("ffmpeg")
    if path is None:
        return None
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return path
    except (subprocess.TimeoutExpired, OSError):
        pass
    return None
