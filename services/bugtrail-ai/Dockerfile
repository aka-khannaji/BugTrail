FROM python:3.11-slim

# llama-cpp-python ships only an sdist on PyPI (needs a C++ compiler). The
# abetlen CPU index hosts prebuilt manylinux wheels, so no compiler is needed.
RUN pip install --no-cache-dir \
      "fastapi>=0.115" "uvicorn>=0.30" "huggingface-hub>=0.24" \
 && pip install --no-cache-dir --only-binary=llama-cpp-python \
      llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu

WORKDIR /app
COPY app /app/app

# Bake the model in at build time so the container runs fully offline.
RUN python -c "from huggingface_hub import hf_hub_download; hf_hub_download('Qwen/Qwen2.5-Coder-0.5B-Instruct-GGUF', 'qwen2.5-coder-0.5b-instruct-q4_k_m.gguf', local_dir='/app/.models'); print('model baked in')" \
 && rm -rf /root/.cache/huggingface

ENV BUGTRAIL_AI_GGUF=/app/.models/qwen2.5-coder-0.5b-instruct-q4_k_m.gguf

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
