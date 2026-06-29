# Use a stable Python base image
FROM python:3.12.13

# Set the working directory inside the container
WORKDIR /app

# Install standard Linux build tools often required by ML libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 1. UPDATED: Copy requirements.txt directly from your root folder
COPY requirements.txt .

# Install your Python packages
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 2. Copy both of your project directories into the container filesystem
COPY plantbgc-service /app/plantbgc-service
COPY PlantBGC-main /app/PlantBGC-main

# 3. Add both folders to the system PYTHONPATH.
# This ensures that 'import src' works for plantbgc-service, 
# AND 'import plantbgc' works for your 10-hour scripts.
ENV PYTHONPATH="/app/plantbgc-service:/app/PlantBGC-main:${PYTHONPATH}"

# Expose the port that FastAPI will run on
EXPOSE 8000