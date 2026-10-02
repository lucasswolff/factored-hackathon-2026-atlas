FROM python:3.12.7-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8765 ADVISOR_HOSTED=1
WORKDIR /app
COPY advisor/ /app/advisor/
COPY plan/conversation_data/source_pack.md /app/plan/conversation_data/source_pack.md
RUN mkdir -p /state && chown -R 10001:10001 /app /state
USER 10001:10001
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import os; from urllib.request import urlopen; assert urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8765') + '/healthz', timeout=3).status == 200"
CMD ["python", "-m", "advisor.web"]
