FROM python:3.11

RUN useradd -m -u 1000 user
WORKDIR /app

COPY --chown=user requirements.txt requirements.txt
RUN pip install --no-cache-dir --upgrade -r requirements.txt

COPY --chown=user . /app

USER user

ENV HOME=/home/user \
	PATH=/home/user/.local/bin:$PATH

EXPOSE 7860

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]