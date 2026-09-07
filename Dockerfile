FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml /app/
COPY trust_network /app/trust_network
RUN pip install --no-cache-dir .
USER 65534:65534
ENTRYPOINT ["python", "-m", "trust_network.demo.worker"]
