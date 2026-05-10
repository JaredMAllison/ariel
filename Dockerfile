FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
ENV PYTHONPATH=/app/core
EXPOSE 8002
CMD ["python3", "-m", "core.orchestrator"]
