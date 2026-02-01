# switchable_persona

This project hosts a Python 3.13 environment for future VLM work (vLLM + VL models).
Note: vLLM officially documents Python 3.10–3.13, but 3.14 works with current wheels.

## Next steps
- Create a virtual environment: `UV_CACHE_DIR=/tmp/uv-cache uv venv --python 3.13 .venv`
- Install/sync core deps (CUDA 13 wheels from the official PyTorch index):
  - `UV_CACHE_DIR=/tmp/uv-cache uv sync --extra vlm`
