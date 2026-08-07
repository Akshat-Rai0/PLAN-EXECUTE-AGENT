# Agent run: from hugging face tell me all the audio to text models that can be run on apples m4 hardware

## Final answer
# Hugging Face Audio-to-Text Models for Apple M4 Hardware

Here's a comprehensive breakdown of models you can run on Apple M4, organized by framework and optimization path.

---

## 1. **Whisper.cpp Core ML Models** (Best for Neural Engine Acceleration)
**Source:** `whisper-cli` repo — prebuilt `.mlmodelc` encoder + GGML weights, optimized for Apple Neural Engine (M1–M5)

| Model | Params | Quantization | Framework | M4 Performance |
|-------|--------|--------------|-----------|----------------|
| `tiny.en` | 39M | INT8/INT4 (GGML) | Core ML (encoder) + GGML (decoder) | **~15–20× realtime** — fastest |
| `base.en` / `base` | 74M | INT8/INT4 | Core ML + GGML | **~10–12× realtime** — great speed/accuracy balance |
| `small.en` / `small` | 244M | INT8/INT4 | Core ML + GGML | **~5–6× realtime** — strong English |
| `medium.en` / `medium` | 769M | INT8/INT4 | Core ML + GGML | **~2–3× realtime** — best quality before large |
| `large-v1` / `v2` / `v3` | 1.5B | INT8/INT4 | Core ML + GGML | **~1.5× realtime** — best multilingual quality |

**How to run:**
```bash
# 1. Download whisper-cli binary (Core ML enabled) from GitHub Releases
# 2. Download model directory (e.g., medium.en/ with .bin + -encoder.mlmodelc/)
chmod +x bin/whisper-cli
./bin/whisper-cli -m medium.en/ggml-medium.en.bin -f audio.wav
```
**Key:** Encoder runs on Neural Engine via Core ML; decoder runs on CPU/GPU via GGML.

---

## 2. **Distil-Whisper (GGUF/GGML)** — 5× Faster than Whisper Large
**Source:** `distil-whisper/distil-large-v3-ggml` on HF Hub

| Model | Size | Quantization | Framework | M4 Notes |
|-------|------|--------------|-----------|----------|
| `distil-large-v3` | ~756M | GGML (INT8/INT4) | Whisper.cpp / Faster-Whisper | **~5× faster than Whisper large-v3**, within 0.8% WER on long-form |

**How to run (Whisper.cpp):**
```bash
git clone https://github.com/ggerganov/whisper.cpp
cd whisper.cpp
pip install --upgrade huggingface_hub
python -c "from huggingface_hub import hf_hub_download; hf_hub_download(repo_id='distil-whisper/distil-large-v3-ggml', filename='ggml-distil-large-v3.bin', local_dir='./models')"
make -j && ./main -m models/ggml-distil-large-v3.bin -f samples/jfk.wav
```

---

## 3. **Hugging Face Core ML Conversions** (`.mlpackage` / `.mlmodelc`)
Models exported via `coremltools` / `huggingface/exporters` — run fully on Neural Engine.

| Model | Type | Quantization | Notes |
|-------|------|--------------|-------|
| `TheStageAI/thewhisper-large-v3-turbo` | Whisper Turbo | Core ML (INT8/INT4) | Turbo variant, faster decoding |
| `aufklarer/Canary-180M-Flash-CoreML` | NVIDIA Canary | Core ML (INT8) | Multilingual ASR + translation |
| `aufklarer/KWS-Zipformer-3M-CoreML-INT8` | Keyword Spotting | Core ML INT8 | Tiny, for wake-word |
| `aufklarer/Silero-VAD-v6.2.1-CoreML` | VAD | Core ML | Voice activity detection |
| `FluidInference/speaker-diarization-coreml` | Diarization | Core ML | Speaker separation |

**Convert your own:** Use `coremltools` (main branch) + `huggingface/exporters` to export any HF `WhisperForConditionalGeneration` model.

---

## 4. **Apple MLX Framework Models** (Native M4 Metal/Unified Memory)
MLX is Apple's array framework optimized for Apple Silicon. Models from `mlx-community` run natively on M4 GPU/CPU.

| Model | Size | Quantization | Type |
|-------|------|--------------|------|
| `mlx-community/parakeet-tdt-0.6b-v3` | 0.6B | BF16/4-bit | NVIDIA Parakeet TDT (streaming ASR) |
| `mlx-community/whisper-large-v3-turbo` | 1.5B | 4-bit/8-bit | Whisper Turbo in MLX |
| `mlx-community/distil-whisper-large-v3` | 756M | 4-bit | Distil-Whisper in MLX |
| `mlx-community/whisper-large-v3` | 1.5B | 4-bit/8-bit | Full Whisper v3 |

**How to run:**
```bash
pip install mlx mlx-audio
# Then use mlx_whisper or mlx_audio APIs
```

---

## 5. **Faster-Whisper / CTranslate2** (CPU/GPU via Metal/MPS)
Not Core ML, but highly optimized C++ inference with INT8 quantization. Runs on M4 CPU/GPU via MPS.

| Model | Quantization | Speed (M1 baseline) |
|-------|--------------|---------------------|
| `large-v3` | INT8 | ~3–4× realtime |
| `distil-large-v3` | INT8 | ~10–15× realtime |

**Install:** `pip install faster-whisper` — auto-detects Metal/MPS on macOS.

---

## 6. **PyTorch + MPS (Metal Performance Shaders)**
Any HF `WhisperForConditionalGeneration` model runs on M4 GPU via `device="mps"`.

```python
from transformers import pipeline
import torch

pipe = pipeline(
    "automatic-speech-recognition",
    model="openai/whisper-large-v3",
    torch_dtype=torch.float16,
    device="mps"  # M4 GPU
)
result = pipe("audio.wav")
```
**Quantization:** Use `bitsandbytes` (MPS support improving) or `torch.compile` + `float16` for speed.

---

## Summary: Which to Choose?

| Priority | Best Option |
|----------|-------------|
| **Max speed (Neural Engine)** | Whisper.cpp Core ML (`tiny.en` → `medium.en`) |
| **Best speed/quality tradeoff** | Distil-Whisper GGML (`distil-large-v3`) |
| **Native Apple framework (MLX)** | `mlx-community/parakeet-tdt-0.6b-v3` or `mlx-community/whisper-large-v3-turbo` |
| **Easiest Python integration** | Faster-Whisper (INT8) or PyTorch MPS |
| **Custom model conversion** | Export via `coremltools` + `huggingface/exporters` → Core ML |

---

## Key Resources
- **Whisper.cpp Core ML models:** `whisper-cli` GitHub Releases
- **Distil-Whisper GGML:** `distil-whisper/distil-large-v3-ggml` on HF Hub
- **Core ML conversions:** Search HF for `coreml` tag + `audio-to-text`
- **MLX models:** `mlx-community` org on HF
- **Conversion guide:** `github.com/huggingface/exporters`

## Steps
### 1. Search for Hugging Face audio-to-text models with Apple Silicon M4 compatibility, Core ML support, or Metal acceleration
- Tool: `web_search`
- Status: `DONE`
### 2. Find Hugging Face models converted to Core ML format (.mlpackage) or optimized for ONNX Runtime on macOS for speech recognition
- Tool: `web_search`
- Status: `DONE`
### 3. Identify GGUF/quantized versions of popular ASR models (Whisper, Distil-Whisper, etc.) that run efficiently on M4 unified memory
- Tool: `web_search`
- Status: `DONE`
### 4. Check for Apple's MLX framework compatible audio models on Hugging Face for native M4 acceleration
- Tool: `web_search`
- Status: `DONE`
### 5. Compile comprehensive list with model names, sizes, quantization options, framework support (Core ML/MLX/ONNX/PyTorch-MPS), and M4 performance notes
- Tool: `none`
- Status: `DONE`

## Artifacts
- No generated workspace files for this run.
- Complete plan, step results, and raw tool output: [`plan.json`](plan.json)
