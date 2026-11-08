FROM python:3.12-alpine@sha256:e064671ca452259bab50e8e2c7bd896e39e9a343bb06ca25234adf6fe18d0fc7
WORKDIR /work
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY exporter.py ./
USER 65532:65532
EXPOSE 9400
CMD ["python", "-u", "exporter.py"]
