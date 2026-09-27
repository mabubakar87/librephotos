#!/bin/bash
mkdir -p /logs
wheel="/protected_media/wheels/llama_cpp_python-0.3.34-py3-none-manylinux_2_35_x86_64.whl"
if [ -f "$wheel" ] && [ "$(stat -c%s "$wheel" 2>/dev/null || echo 0)" = "1870025135" ]; then
  if ! python /opt/librephotos/ensure_llama_cuda.py >> /logs/llama-cuda.log 2>&1; then
    echo "llama CUDA install failed; see /logs/llama-cuda.log" >> /logs/llama-cuda.log
  fi
else
  echo "llama CUDA wheel is not ready; Moondream and Mistral stay on the processor for this start" >> /logs/llama-cuda.log
fi
nohup /bin/bash /keep-workers.sh >> /logs/keep-workers.log 2>&1 &
exec /entrypoint.sh
