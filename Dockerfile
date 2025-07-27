# Use an official Python base image
FROM python:3.11-slim

# Set environment variables for GUI support
ENV DEBIAN_FRONTEND=noninteractive
ENV DISPLAY=:0

# Install system packages required for tkinter and X11 GUI apps
RUN apt-get update && apt-get install -y \
    python3-tk \
    tk-dev \
    libx11-dev \
    libxext-dev \
    libxrender-dev \
    libxtst-dev \
    libxi-dev \
    libgl1-mesa-glx \
    libgl1-mesa-dri \
    libgtk-3-0 \
    build-essential \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files into the container
COPY . /app

# Install Python packages from requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Run your main Python file
CMD ["python", "proj.py"]
