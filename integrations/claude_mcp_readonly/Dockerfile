FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN python -m pip install --no-cache-dir 'mcp>=2.0,<3' 'uvicorn>=0.30,<1' 'starlette>=0.40,<1'
WORKDIR /srv/app
COPY server.py /srv/app/server.py
USER 65534:65534
EXPOSE 8765
CMD ["uvicorn","server:app","--host","0.0.0.0","--port","8765","--workers","1","--no-access-log"]
