"""Pick the GPU only when this machine has a usable NVIDIA card.

The check is the same for every model service: a card must be visible, have
at least 8 GB of memory, and report compute capability 7.0 or newer. Anything
else stays on the processor, including a missing driver or a CPU-only build.
"""

import subprocess

MIN_VRAM_MB = 8192
MIN_COMPUTE_CAPABILITY = 7.0


def _query_gpu():
    try:
        output = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.total,compute_cap",
                "--format=csv,noheader,nounits",
            ],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    best = None
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 2:
            continue
        try:
            memory_mb = float(parts[0])
            compute_cap = float(parts[1])
        except ValueError:
            continue
        if best is None or memory_mb > best[0]:
            best = (memory_mb, compute_cap)
    return best


def gpu_is_capable():
    info = _query_gpu()
    if info is None:
        return False
    memory_mb, compute_cap = info
    return memory_mb >= MIN_VRAM_MB and compute_cap >= MIN_COMPUTE_CAPABILITY


def onnx_providers():
    if not gpu_is_capable():
        return ["CPUExecutionProvider"]
    try:
        import onnxruntime as ort
    except ImportError:
        return ["CPUExecutionProvider"]
    if "CUDAExecutionProvider" in ort.get_available_providers():
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


def use_torch_cuda():
    if not gpu_is_capable():
        return False
    try:
        import torch
    except ImportError:
        return False
    return bool(torch.cuda.is_available())


def llama_gpu_layers():
    """Return -1 to offload every layer, or 0 to stay on the processor."""
    if not gpu_is_capable():
        return 0
    try:
        import llama_cpp
    except ImportError:
        return 0
    if llama_cpp.llama_supports_gpu_offload():
        return -1
    return 0
