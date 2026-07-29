FROM python:3.13-slim

WORKDIR /app

# graphifyy installs ~30 tree-sitter grammars it only needs for extraction, which
# happens on the host. --no-deps keeps the serving image at a fraction of that.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && pip install --no-cache-dir --no-deps graphifyy

COPY server.py .

ENV EXPERT_PORT=8800
EXPOSE 8800

CMD ["python", "server.py"]
