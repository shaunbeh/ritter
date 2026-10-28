FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app \
    HF_HOME=/cache/huggingface \
    HUGGINGFACE_HUB_CACHE=/cache/huggingface \
    NLTK_DATA=/cache/nltk \
    WHISPER_DOWNLOAD_ROOT=/cache/whisper

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
        ffmpeg \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

# CUDA wheels first. whisperx depends on torch 2.8 and would otherwise pull a mismatched build.
RUN pip install --no-cache-dir \
        torch==2.8.0 \
        torchaudio==2.8.0 \
        torchvision==0.23.0 \
        --index-url https://download.pytorch.org/whl/cu128

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --force-reinstall \
        torch==2.8.0 \
        torchaudio==2.8.0 \
        torchvision==0.23.0 \
        --index-url https://download.pytorch.org/whl/cu128

# PyTorch's pip packages ship cuDNN beside site-packages. Register them with the loader.
RUN python - <<'PY'
import pathlib, site
libs = []
for base in site.getsitepackages():
    nvidia = pathlib.Path(base) / "nvidia"
    if nvidia.is_dir():
        libs.extend(str(path) for path in nvidia.glob("*/lib") if path.is_dir())
pathlib.Path("/etc/ld.so.conf.d/nvidia-pip.conf").write_text("\n".join(libs) + "\n")
print("\n".join(libs))
PY
RUN ldconfig

COPY app ./app

RUN mkdir -p /cache/huggingface /cache/nltk /cache/whisper

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
