# Use Python 3.11 slim base image for smaller size
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir poetry==1.7.1

# Copy dependency files
COPY pyproject.toml ./

# Configure Poetry to not create virtual environment (we're in a container)
RUN poetry config virtualenvs.create false

# Install dependencies (will generate poetry.lock if not present)
RUN poetry install --only main --no-interaction --no-ansi

# Copy application code
COPY src/ ./src/
COPY .env.example ./.env.example

# Create non-root user for security
RUN useradd -m -u 1000 monitor && \
    chown -R monitor:monitor /app

# Switch to non-root user
USER monitor

# Expose port 8000 for API
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/api/v1/health', timeout=5)" || exit 1

# Run main application
CMD ["python", "-m", "uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
