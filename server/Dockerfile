FROM docker.m.daocloud.io/library/python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --index-url https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
COPY . .

EXPOSE 5100
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "5100"]
