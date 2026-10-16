FROM python:3.12-alpine

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app \
    MODOOR_ADDON_ROOT=/app/addon \
    MODOOR_PLATFORM_ROOT=/app/builtin \
    MODOOR_WEBUI_URL=http://127.0.0.1:8765 \
    MODOOR_WEBUI_PROXIES= \
    MODOOR_DOC_OCR=0 \
    MODOOR_OCR_BACKEND=tesseract \
    MODOOR_PY_CACHE=/var/cache/modoor/py

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY modoor modoor
COPY builtin builtin
COPY addon addon

RUN pip install --no-cache-dir --no-compile . \
 && python - <<'PY'
import pathlib, shutil
root = pathlib.Path("/usr/local/lib/python3.12")
sp = root / "site-packages"
# App code is imported from /app. Drop the copy pip just installed.
for name in ("modoor", "builtin", "addon", "external"):
    shutil.rmtree(sp / name, ignore_errors=True)
for path in sp.glob("modoor-*.dist-info"):
    shutil.rmtree(path, ignore_errors=True)
shutil.rmtree(sp / "sqlalchemy" / "testing", ignore_errors=True)
for name in ("idlelib", "tkinter", "turtledemo", "ensurepip"):
    shutil.rmtree(root / name, ignore_errors=True)
turtle = root / "turtle.py"
turtle.unlink(missing_ok=True)
PY

ARG MODOOR_WEBUI_STATIC_MODULES=base
ENV MODOOR_WEBUI_STATIC_MODULES=${MODOOR_WEBUI_STATIC_MODULES}

COPY logo.png /app/logo.png
COPY scripts/docker-entrypoint.sh /usr/local/bin/modoor-entrypoint
RUN chmod +x /usr/local/bin/modoor-entrypoint

EXPOSE 8765

ENTRYPOINT ["modoor-entrypoint"]
CMD ["python", "-m", "uvicorn", "modoor.web.app:app", "--host", "0.0.0.0", "--port", "8765", "--proxy-headers"]
