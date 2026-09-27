"""Install the CUDA build of llama-cpp-python when the GPU check passes.

The published GPU image still ships a processor-only llama.cpp, so Moondream
and Mistral would ignore the card. The wheel is kept on the data volume so a
later container start does not download it again. If the GPU is not capable,
the processor build is left alone.

A failed pip install can leave llama-cpp-python in a broken state (missing
shared library). This script uninstalls that build and reinstalls from the
cached wheel before the API starts.
"""

import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, "/opt/librephotos")
import gpu_runtime

WHEEL_NAME = "llama_cpp_python-0.3.34-py3-none-manylinux_2_35_x86_64.whl"
WHEEL_SIZE = 1870025135
WHEEL_URL = (
    "https://github.com/abetlen/llama-cpp-python/releases/download/"
    f"v0.3.34-cu121/{WHEEL_NAME}"
)
WHEEL_DIR = Path("/protected_media/wheels")
PIP = [
    sys.executable,
    "-m",
    "pip",
    "--no-cache-dir",
    "--break-system-packages",
]


def _clear_llama_modules():
    for name in list(sys.modules):
        if name == "llama_cpp" or name.startswith("llama_cpp."):
            del sys.modules[name]


def llama_offload_available():
    _clear_llama_modules()
    try:
        import llama_cpp
    except Exception as exc:
        print(f"llama: import failed ({exc})")
        return False
    try:
        return bool(llama_cpp.llama_supports_gpu_offload())
    except Exception as exc:
        print(f"llama: GPU offload check failed ({exc})")
        return False


def uninstall_llama():
    print("llama: removing the existing llama-cpp-python package")
    subprocess.run(
        [*PIP, "uninstall", "-y", "llama-cpp-python"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    _clear_llama_modules()


def ensure_wheel():
    WHEEL_DIR.mkdir(parents=True, exist_ok=True)
    wheel = WHEEL_DIR / WHEEL_NAME
    if wheel.is_file() and wheel.stat().st_size == WHEEL_SIZE:
        return wheel
    partial = wheel.with_suffix(wheel.suffix + ".partial")
    print(f"llama: downloading {WHEEL_NAME}")
    urllib.request.urlretrieve(WHEEL_URL, partial)
    size = partial.stat().st_size
    if size != WHEEL_SIZE:
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"llama: downloaded wheel size {size} != {WHEEL_SIZE}")
    partial.replace(wheel)
    return wheel


def install_wheel(wheel: Path):
    print(f"llama: installing the CUDA build from {wheel}")
    subprocess.check_call(
        [
            *PIP,
            "install",
            "--force-reinstall",
            "--no-deps",
            str(wheel),
        ]
    )
    _clear_llama_modules()


def main():
    if not gpu_runtime.gpu_is_capable():
        print("llama: GPU check failed, leaving the processor build in place")
        return 0

    if llama_offload_available():
        print("llama: GPU offload already available")
        return 0

    wheel = ensure_wheel()
    uninstall_llama()
    try:
        install_wheel(wheel)
    except subprocess.CalledProcessError as exc:
        print(f"llama: pip install failed with exit code {exc.returncode}")
        return 1

    if llama_offload_available():
        print("llama: GPU offload is available after install")
        return 0

    print("llama: install finished but GPU offload is still unavailable")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
