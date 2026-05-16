FROM python:3.12-slim
LABEL org.opencontainers.image.title="cognis-k8scost"
LABEL org.opencontainers.image.source="https://github.com/cognis-digital/k8scost"
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir .
ENTRYPOINT ["k8scost"]
