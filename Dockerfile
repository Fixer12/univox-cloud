FROM python:3.12-slim-bookworm

# AVR compiler and the Arduino core (no downloads from other sites needed)
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc-avr avr-libc binutils-avr arduino-core-avr \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# all files sit side by side in the repository; put them into the app folder here
COPY main.py ai.py compiler.py prompts.py samples.py validate.py univox.h ./app/
COPY index.html ./app/static/index.html
RUN touch app/__init__.py

# build the Arduino core once while the image is built, so the first request is fast
RUN python -c "from app.compiler import compile_sketch; r = compile_sketch('#include \"univox.h\"\nvoid setup(){univoxBegin();}\nvoid loop(){}'); print(r.ok, r.log); assert r.ok"

ENV PORT=10000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
