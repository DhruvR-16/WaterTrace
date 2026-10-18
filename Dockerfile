FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY watertrace ./watertrace
RUN useradd --create-home --uid 10001 watertrace
USER watertrace
ENV WATERTRACE_DEPLOYMENT=local-container WATERTRACE_DATA=/data PYTHONDONTWRITEBYTECODE=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"
CMD ["uvicorn", "watertrace.main:app", "--host", "0.0.0.0", "--port", "8000"]
