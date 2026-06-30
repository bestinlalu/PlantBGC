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

# 2. Copy the project directory into the container filesystem.
# bgc_web only serves the API/frontend — it never runs plantbgc directly
# (that's bgc_worker's job, via the pip-installed plantbgc package)
COPY plantbgc-service /app/plantbgc-service

# 3. Add plantbgc-service to PYTHONPATH so 'import src' works.
ENV PYTHONPATH="/app/plantbgc-service:${PYTHONPATH}"

# Expose the port that FastAPI will run on
EXPOSE 8000