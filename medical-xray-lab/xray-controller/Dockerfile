FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY controller.py xray_openplc.st ./

EXPOSE 5020

CMD ["python", "controller.py"]
