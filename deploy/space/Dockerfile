FROM python:3.11-slim

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    HF_HOME=/home/user/.cache/huggingface
WORKDIR $HOME/app

# PyTorch versi CPU (jauh lebih kecil daripada versi CUDA)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Muat turun model semasa build supaya permulaan server lebih cepat
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-base')"

COPY --chown=user . .
EXPOSE 7860
CMD ["uvicorn", "api:app", "--app-dir", "src/app", "--host", "0.0.0.0", "--port", "7860"]