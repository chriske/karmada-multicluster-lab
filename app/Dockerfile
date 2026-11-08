FROM python:3.12-alpine@sha256:e064671ca452259bab50e8e2c7bd896e39e9a343bb06ca25234adf6fe18d0fc7
WORKDIR /work
COPY server.py load.py ./
EXPOSE 8080
CMD ["python", "-u", "server.py"]
