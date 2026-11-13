import os
import re
import secrets
import threading
import time
import uuid
from collections import OrderedDict, defaultdict, deque

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import ai
from .compiler import compile_sketch, toolchain_ready
from .validate import check_sketch

HERE = os.path.dirname(os.path.abspath(__file__))
ACCESS_CODE = os.getenv("ACCESS_CODE", "")          # shared password so strangers cannot use your AI credit
MAX_ATTEMPTS = 3                                     # first try + 2 automatic fixes
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_HOUR", "20"))

app = FastAPI(title="AI Command Based Switching Automation Device")

# last compiled programs, kept in memory (the ESP-12E downloads the hex from here in a later stage)
JOBS: "OrderedDict[str, dict]" = OrderedDict()
JOBS_LOCK = threading.Lock()
_hits = defaultdict(deque)


def check_access(x_access_code: str = Header(default="")):
    if not ACCESS_CODE:
        return
    if not secrets.compare_digest(x_access_code.encode(), ACCESS_CODE.encode()):
        raise HTTPException(status_code=401, detail="Wrong or missing access code.")


def rate_limit(request: Request):
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0].strip()
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="Too many requests this hour. Try again later.")
    q.append(now)


class CommandIn(BaseModel):
    text: str = Field(min_length=3, max_length=600)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "compiler_ready": toolchain_ready(),
        "ai_ready": ai.ai_ready(),
        "mock_mode": ai.MOCK,
        "model": ai.MODEL,
        "access_code_required": bool(ACCESS_CODE),
    }


@app.post("/api/generate", dependencies=[Depends(check_access), Depends(rate_limit)])
def generate(cmd: CommandIn):
    text = re.sub(r"\s+", " ", cmd.text).strip()
    sketch, last_errors, data, comp, attempts = "", "", {}, None, 0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        attempts = attempt
        try:
            data = ai.generate(text, previous_sketch=sketch, errors=last_errors)
        except ai.AIError as e:
            raise HTTPException(status_code=503, detail=str(e))
        sketch = data["sketch"]
        problems = check_sketch(sketch)
        if problems:
            last_errors = "Rule check failed:\n- " + "\n- ".join(problems)
            comp = None
            continue
        comp = compile_sketch(sketch)
        if comp.ok:
            break
        last_errors = "Compiler errors:\n" + comp.log
    ok = bool(comp and comp.ok)
    job_id = None
    if ok:
        job_id = uuid.uuid4().hex[:12]
        with JOBS_LOCK:
            JOBS[job_id] = {"hex": comp.hex_text, "title": data.get("title", ""), "created": time.time()}
            while len(JOBS) > 20:
                JOBS.popitem(last=False)
    return {
        "ok": ok,
        "attempts": attempts,
        "title": data.get("title", ""),
        "explanation": data.get("explanation", ""),
        "wiring": data.get("wiring", []),
        "sketch": sketch,
        "compile": {
            "ok": ok,
            "message": comp.log if comp else last_errors,
            "flash_bytes": comp.flash_bytes if comp else 0,
            "flash_percent": comp.flash_pct if comp else 0,
            "ram_bytes": comp.ram_bytes if comp else 0,
            "ram_percent": comp.ram_pct if comp else 0,
        },
        "job_id": job_id,
        "error": None if ok else "The program could not be built after several tries. Last problem: " + last_errors[:500],
    }


@app.get("/api/jobs/{job_id}/hex", dependencies=[Depends(check_access)], response_class=PlainTextResponse)
def job_hex(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Unknown or expired job.")
    return job["hex"]


app.mount("/static", StaticFiles(directory=os.path.join(HERE, "static")), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(HERE, "static", "index.html"))
