FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY fetch_xrays.py app.py ./

# Pre-fetch and filter X-ray images from HumynLabs/medical-imaging and robailleo/medical-imaging-combined
RUN python fetch_xrays.py

EXPOSE 8080

CMD ["python", "app.py"]
