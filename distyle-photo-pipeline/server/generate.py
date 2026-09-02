"""Generate a new catalog sofa shot from a reference photo (not a crop)."""

from __future__ import annotations

import io
import os
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageOps

from dotenv import load_dotenv
from pathlib import Path as _P

load_dotenv()
load_dotenv(_P(__file__).resolve().parents[1] / ".env")

from cutout import _bg_color

# Kontext is an EDIT model: preserve product, change only background.
# Short "catalog photo of this sofa" prompts make it reinvent the product.
LOCAL_PROMPT = (
    "Keep this exact sofa unchanged: same shape, proportions, armrests, legs, "
    "seams, piping, fabric color and weave, and the same pillows only — "
    "do not add, remove, or invent pillows or a blanket. "
    "Change only the background to a seamless solid studio backdrop #edece8 "
    "with no wall, no horizon line, no carpet texture, no room, no extra furniture. "
    "Keep front-on eye-level camera. Soft contact shadow under the sofa only. "
    "Photoreal fabric, sharp seams, no melted or blotchy texture."
)

# One prompt. Do not stack extra instructions on top — contradictions
# (front vs 3/4, cutout vs photograph, center vs floor) ruin seams and edges.
PROMPT = (
    "Photorealistic square 1:1 furniture catalog photograph of the exact same sofa "
    "as in the reference images. Keep that product only: the same overall shape, "
    "module layout, armrests, legs, seams, piping, fabric color and texture, and the "
    "same pillows. Do not invent a different model and do not turn a sofa into an armchair. "
    "Camera at backrest height, looking straight at the front of the sofa, eye-level, "
    "not from the side, not a 3/4 angle, not from above. The complete sofa sits in the "
    "lower-middle of the frame and fills most of the width, with even empty space on "
    "left and right. Seamless solid studio background #edece8 with no wall, no horizon, "
    "no room, no extra furniture, no people, no text. One soft natural contact shadow "
    "on the floor under the sofa, same color family as the background. Photograph the "
    "sofa already in the studio — do not cut, mask, or collage. Sharp clean seams and "
    "fabric, no white fringe, no dark outline, no pixelated or dotted edges."
)


def _to_studio_webp(img: Image.Image, width: int, height: int, quality: int) -> bytes:
    """Letterbox onto studio canvas. Never rembg / choke / crop the sofa."""
    bg = _bg_color()
    rgb = img.convert("RGB")
    if rgb.size == (width, height):
        fitted = rgb
    else:
        contained = ImageOps.contain(rgb, (width, height), Image.BICUBIC)
        fitted = Image.new("RGB", (width, height), bg)
        fitted.paste(
            contained,
            ((width - contained.width) // 2, (height - contained.height) // 2),
        )
    buf = io.BytesIO()
    fitted.save(buf, format="WEBP", lossless=True, method=6)
    return buf.getvalue()


def _decode_image_bytes(data: bytes) -> Image.Image:
    return Image.open(io.BytesIO(data)).convert("RGBA")


def _try_gemini(ref: bytes, extra_parts: List[bytes]) -> Optional[bytes]:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return None
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        return None

    client = genai.Client(api_key=api_key)
    parts: List[Any] = [types.Part.from_bytes(data=ref, mime_type="image/jpeg")]
    for p in extra_parts[:2]:
        parts.append(types.Part.from_bytes(data=p, mime_type="image/jpeg"))
    parts.append(PROMPT)
    models = [
        os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image"),
        "gemini-2.5-flash-image-preview",
        "gemini-2.0-flash-preview-image-generation",
    ]
    last_err = None
    for model in models:
        try:
            response = client.models.generate_content(
                model=model,
                contents=parts,
                config=types.GenerateContentConfig(response_modalities=["IMAGE", "TEXT"]),
            )
            for cand in getattr(response, "candidates", None) or []:
                content = getattr(cand, "content", None)
                for part in getattr(content, "parts", None) or []:
                    inline = getattr(part, "inline_data", None)
                    if inline and getattr(inline, "data", None):
                        return inline.data
        except Exception as e:
            last_err = e
            continue
    if last_err:
        raise last_err
    return None


def _try_openai(ref: bytes) -> Optional[bytes]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None

    client = OpenAI(api_key=api_key)
    img_file = io.BytesIO(ref)
    img_file.name = "reference.jpg"
    result = client.images.edit(
        model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1"),
        image=img_file,
        prompt=PROMPT,
        size="1024x1024",
    )
    b64 = result.data[0].b64_json
    import base64

    return base64.b64decode(b64)


def _try_hf(ref: bytes) -> Optional[bytes]:
    token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN")
    if not token:
        return None
    try:
        from huggingface_hub import InferenceClient
    except ImportError:
        return None

    client = InferenceClient(token=token)
    model = os.getenv("HF_IMAGE_MODEL", "black-forest-labs/FLUX.1-schnell")
    out = client.image_to_image(ref, prompt=PROMPT, model=model)
    if isinstance(out, Image.Image):
        buf = io.BytesIO()
        out.convert("RGB").save(buf, format="PNG")
        return buf.getvalue()
    if isinstance(out, bytes):
        return out
    return None


_local_pipe = None
_local_pipe_kind: Optional[str] = None


def _hf_token() -> Optional[str]:
    return os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN") or None


def _local_device() -> str:
    import torch

    forced = os.getenv("LOCAL_IMAGE_DEVICE", "").strip().lower()
    if forced:
        return forced
    return "cuda" if torch.cuda.is_available() else "cpu"


def _prepare_ref_image(ref: bytes, max_side: int | None = None) -> Image.Image:
    if max_side is None:
        # 1024 is the quality floor for FLUX; 768 looked melted after upscale.
        max_side = int(os.getenv("LOCAL_IMAGE_MAX_SIDE", "1024"))
    img = Image.open(io.BytesIO(ref)).convert("RGB")
    img.thumbnail((max_side, max_side), Image.BICUBIC)
    return img


def _load_local_pipe():
    global _local_pipe, _local_pipe_kind
    if _local_pipe is not None:
        return _local_pipe, _local_pipe_kind

    import torch

    model = os.getenv("LOCAL_IMAGE_MODEL", "black-forest-labs/FLUX.1-Kontext-dev")
    device = _local_device()
    model_lower = model.lower()
    token = _hf_token()
    load_kw: Dict[str, Any] = {"token": token} if token else {}
    dtype = torch.bfloat16 if device == "cuda" else torch.float32
    load_kw["dtype"] = dtype

    if "kontext" in model_lower:
        from diffusers import FluxKontextPipeline

        pipe = FluxKontextPipeline.from_pretrained(model, **load_kw)
        kind = "flux_kontext"
    elif "flux" in model_lower:
        from diffusers import FluxImg2ImgPipeline

        pipe = FluxImg2ImgPipeline.from_pretrained(model, **load_kw)
        kind = "flux_i2i"
    else:
        from diffusers import AutoPipelineForImage2Image

        if device == "cuda":
            load_kw["variant"] = "fp16"
            load_kw["dtype"] = torch.float16
        pipe = AutoPipelineForImage2Image.from_pretrained(model, **load_kw)
        kind = "sd_i2i"

    # Without Ollama, model offload usually fits 24GB and looks better than sequential.
    offload_mode = os.getenv(
        "LOCAL_IMAGE_OFFLOAD",
        "model" if kind == "flux_kontext" else "model",
    ).lower()
    if device == "cuda" and offload_mode in ("sequential", "model", "1", "true", "yes"):
        if offload_mode == "sequential":
            pipe.enable_sequential_cpu_offload()
        else:
            pipe.enable_model_cpu_offload()
    elif device == "cuda":
        pipe = pipe.to(device)
    else:
        pipe = pipe.to(device)

    _local_pipe = pipe
    _local_pipe_kind = kind
    return pipe, kind


def _run_local_pipe(pipe, kind: str, img: Image.Image) -> Image.Image:
    steps = int(os.getenv("LOCAL_IMAGE_STEPS", "32" if "flux" in kind else "4"))
    # Lower guidance = less reinventing the product (Kontext over-edits at high CFG).
    guidance = float(os.getenv("LOCAL_IMAGE_GUIDANCE", "2.0"))
    strength = float(os.getenv("LOCAL_IMAGE_STRENGTH", "0.55"))
    out_side = int(os.getenv("LOCAL_IMAGE_OUT_SIDE", "1024"))
    negative = "room, interior, curtains, table, rug, carpet, lamp, people, text, watermark"

    if kind == "flux_kontext":
        return pipe(
            image=img,
            prompt=LOCAL_PROMPT,
            num_inference_steps=max(steps, 4),
            guidance_scale=guidance,
            width=out_side,
            height=out_side,
        ).images[0]

    if kind == "flux_i2i":
        return pipe(
            prompt=LOCAL_PROMPT,
            image=img,
            num_inference_steps=max(steps, 4),
            strength=strength,
            guidance_scale=guidance,
            width=out_side,
            height=out_side,
        ).images[0]

    gen_kwargs: Dict[str, Any] = {
        "prompt": LOCAL_PROMPT,
        "image": img,
        "num_inference_steps": max(steps, 2),
        "strength": strength,
        "negative_prompt": negative,
    }
    model = os.getenv("LOCAL_IMAGE_MODEL", "")
    if "turbo" in model.lower():
        gen_kwargs["guidance_scale"] = 0.0
    return pipe(**gen_kwargs).images[0]


def _try_local(ref: bytes) -> Optional[bytes]:
    """Local img2img — FLUX Kontext on RunPod CUDA, sd-turbo fallback on CPU."""
    if not _local_available():
        return None

    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass

    pipe, kind = _load_local_pipe()
    img = _prepare_ref_image(ref)
    out = _run_local_pipe(pipe, kind, img)
    buf = io.BytesIO()
    out.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def _local_available() -> bool:
    if os.getenv("LOCAL_IMAGE_GEN", "1").lower() in ("0", "false", "off"):
        return False
    try:
        import diffusers  # noqa: F401
        import torch  # noqa: F401
    except ImportError:
        return False
    return True


def available_backend() -> str:
    if _local_available():
        model = os.getenv("LOCAL_IMAGE_MODEL", "black-forest-labs/FLUX.1-Kontext-dev")
        if "kontext" in model.lower():
            return "local:flux-kontext"
        if "flux" in model.lower():
            return "local:flux"
        return "local:sd"
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        return "gemini"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN"):
        return "hf"
    return "missing"


def _try_cache(product_id: Optional[int]) -> Optional[bytes]:
    if not product_id:
        return None
    cache = _P(__file__).resolve().parents[1] / "client" / "_gen_cache"
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        path = cache / f"{product_id}{ext}"
        if path.exists():
            return path.read_bytes()
    return None


def process_generate(
    image_bytes: bytes,
    extra_refs: Optional[List[bytes]] = None,
    width: int = 1920,
    height: int = 1920,
    quality: int = 95,
    product_id: Optional[int] = None,
) -> Tuple[bytes, Dict[str, Any]]:
    extra_refs = extra_refs or []
    raw = None
    backend = available_backend()
    errors: List[str] = []

    # Local first (no paid API). Cache is last resort — old Cursor files must not skip local.
    for name in ("local", "gemini", "openai", "hf"):
        try:
            if name == "local":
                raw = _try_local(image_bytes)
            elif name == "gemini":
                raw = _try_gemini(image_bytes, extra_refs)
            elif name == "openai":
                raw = _try_openai(image_bytes)
            else:
                raw = _try_hf(image_bytes)
            if raw:
                backend = name
                break
        except Exception as e:
            errors.append(f"{name}: {e}")

    if not raw:
        raw = _try_cache(product_id)
        if raw:
            backend = "cache"

    if not raw:
        hint = (
            "Nera generate backend. RunPod: LOCAL_IMAGE_DEVICE=cuda, "
            "LOCAL_IMAGE_MODEL=black-forest-labs/FLUX.1-Kontext-dev, HF_TOKEN. "
            "Laptop CPU: LOCAL_IMAGE_MODEL=stabilityai/sd-turbo."
        )
        raise RuntimeError(hint + ((" | " + " ; ".join(errors)) if errors else ""))

    img = _decode_image_bytes(raw)
    webp = _to_studio_webp(img, width, height, quality)
    return webp, {"valid": True, "method": "generate", "backend": backend}
