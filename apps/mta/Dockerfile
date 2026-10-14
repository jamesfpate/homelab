FROM python:3.12-slim
RUN pip install --no-cache-dir gtfs-realtime-bindings==1.0.0 paho-mqtt==2.1.0 requests==2.34.2
COPY mta.py /app/mta.py
ENV PYTHONUNBUFFERED=1
CMD ["python3", "/app/mta.py"]
