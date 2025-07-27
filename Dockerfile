# Use an official Python image
FROM python:3.11-slim

# Environment settings for GUI
ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:0

# Install system dependencies required for tkinter and GUI
RUN apt-get update && apt-get install -y \
    python3-tk \
    tk \
    libx11-dev \
    libxext-dev \
    libxrender-dev \
    libxtst-dev \
    libxi-dev \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Create working directory
WORKDIR /app

# Copy current directory contents into the container
COPY . /app

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Run the application
CMD ["python", "proj.py"]
