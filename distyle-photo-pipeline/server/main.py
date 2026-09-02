"""FastAPI AI server: vision scoring + cutout."""

from __future__ import annotations

import base64
import logging
import os
from typing import List, Optional

from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response

from cutout import process_cutout
from generate import available_backend, process_generate
from image_heuristics import score_image_heuristics
from vision_ollama import check_ollama, combined_score, score_with_ollama

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="DiStyle AI Server", version="1.1.0")

API_KEY = os.getenv("CUTOUT_API_KEY", "local-test-key")


def verify_key(x_api_key: Optional[str] = Header(None)) -> None:
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/health")
def health():
    ollama = check_ollama()
    cutout_ok = True
    try:
        import rembg  # noqa: F401
    except ImportError:
        cutout_ok = False

    return {
        "status": "ok",
        "ollama": ollama.get("status", "unknown"),
        "ollama_model": os.getenv("OLLAMA_MODEL", "llava"),
        "cutout": "ok" if cutout_ok else "rembg_missing",
        "generate": available_backend(),
    }


@app.post("/vision/score", dependencies=[Depends(verify_key)])
async def vision_score(file: UploadFile = File(...)):
    """Score image for sofa photo suitability (heuristics + Ollama)."""
    data = await file.read()
    heur = score_image_heuristics(data)
    ollama = score_with_ollama(data)
    ollama_score = ollama.get("ollama_score")
    final = combined_score(
        heur["heuristic_score"],
        ollama_score,
        heuristic_reject=heur.get("reject", False),
    )
    # Hard reject only from heuristics; Ollama adjusts score but cutout is final gate
    rejected = heur.get("reject", False)
    if ollama_score is not None and ollama_score < 35:
        rejected = True

    return {
        "score": final,
        "heuristic_score": heur["heuristic_score"],
        "ollama_score": ollama_score,
        "reject": rejected,
        "heuristic_details": heur,
        "ollama_details": ollama,
    }


@app.post("/cutout", dependencies=[Depends(verify_key)])
async def cutout(
    file: UploadFile = File(...),
    width: int = 1920,
    height: int = 1920,
    quality: int = 95,
    meta: bool = False,
):
    """Remove background, apply studio BG. Pass meta=true for JSON with validation."""
    data = await file.read()
    try:
        result_bytes, cutout_meta = process_cutout(data, width=width, height=height, quality=quality)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if meta:
        return JSONResponse({
            "valid": cutout_meta.get("valid", False),
            "meta": cutout_meta,
            "webp_b64": base64.b64encode(result_bytes).decode(),
        })

    return Response(content=result_bytes, media_type="image/webp")


@app.post("/generate", dependencies=[Depends(verify_key)])
async def generate(
    file: UploadFile = File(...),
    refs: List[UploadFile] = File(default=[]),
    width: int = 1920,
    height: int = 1920,
    quality: int = 95,
    product_id: Optional[int] = None,
):
    """Create a new studio sofa photo from a reference (not a crop)."""
    data = await file.read()
    extra: list[bytes] = []
    if refs:
        for ref in refs[:2]:
            extra.append(await ref.read())
    try:
        result_bytes, gen_meta = process_generate(
            data,
            extra_refs=extra,
            width=width,
            height=height,
            quality=quality,
            product_id=product_id,
        )
    except Exception as e:
        logger.exception("generate failed product_id=%s", product_id)
        raise HTTPException(status_code=500, detail=str(e))

    return JSONResponse({
        "valid": gen_meta.get("valid", True),
        "meta": gen_meta,
        "webp_b64": base64.b64encode(result_bytes).decode(),
    })


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8765"))
    uvicorn.run("main:app", host=host, port=port, reload=False)
