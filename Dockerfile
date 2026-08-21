# 1. Base Image: Choose a lightweight official Python base image
FROM python:3.11-slim

# 2. Environment Variables: Prevent Python from writing .pyc files & buffer logs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 3. Working Directory: Set the internal container directory
WORKDIR /app

# 4. System Dependencies: Install compiler tools required by native libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 5. Dependency Layer Caching: Copy and install Python packages first
# Change this line:
# 5. Dependency Layer Caching: Copy and install Python packages first
COPY backend/app/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 6. Source Code: Copy project files into the container
COPY . .

# 7. Port Declaration: Document exposed ports (FastAPI & Streamlit)
EXPOSE 8000 8501

# 8. Start Command: Launch both services concurrently
CMD ["sh", "-c", "python -m uvicorn backend.app.app:app --host 0.0.0.0 --port 8000 & streamlit run frontend/app.py --server.port 8501 --server.address 0.0.0.0"]