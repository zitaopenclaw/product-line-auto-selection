FROM python:3.11-slim

RUN useradd -m -u 1000 user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user src/ ./src/
COPY --chown=user prompts/ ./prompts/
COPY --chown=user output/advanced_pn_tree.json ./output/advanced_pn_tree.json
COPY --chown=user app.py .

USER user

EXPOSE 7860

CMD PORT=${PORT:-7860}; python -m uvicorn app:app --host 0.0.0.0 --port $PORT