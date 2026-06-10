FROM python:3.10-slim
RUN apt-get update && apt-get install -y ffmpeg libopus-dev git curl unzip \
    && curl -fsSL https://deno.land/install.sh | sh
ENV PATH="/root/.deno/bin:$PATH"
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "bot.py"]
