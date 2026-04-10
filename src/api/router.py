"""
Model Switching Logic + Auto Fallback — Chọn model đúng trên UI Gemini.

Quy trình:
1. Quét danh sách model khả dụng trên UI
2. Match model yêu cầu với danh sách
3. Nếu không match → tự động fallback theo thứ tự ưu tiên
4. Trả metadata về model thực tế đã chọn
"""

from __future__ import annotations

import logging
from typing import Optional
from dataclasses import dataclass

from src.core.client import GeminiClient
from src.core.adapter import (
    normalize_model_name,
    match_model_in_list,
    FALLBACK_ORDER,
    MODEL_ALIASES,
)

logger = logging.getLogger("model_router")


@dataclass
class ModelSwitchResult:
    """Kết quả sau khi chọn/chuyển model."""
    success: bool
    requested_model: str          # Model client yêu cầu
    actual_model: str             # Model thực tế đã chọn trên UI
    actual_model_normalized: str  # Tên chuẩn hóa (gemini-pro, gemini-flash...)
    fallback: bool = False        # Có phải fallback không
    fallback_reason: str = ""     # Lý do fallback


async def select_best_model(
    client: GeminiClient,
    requested_model: str,
    current_model: str = "",
) -> ModelSwitchResult:
    """
    Chọn model tốt nhất có thể trên giao diện Gemini Web.

    Logic:
    1. Nếu model hiện tại đã đúng → skip (không cần click)
    2. Quét danh sách model khả dụng
    3. Match model yêu cầu
    4. Nếu không match → fallback theo thứ tự ưu tiên
    """
    normalized = normalize_model_name(requested_model)

    # Nếu đang ở đúng model rồi → không cần chuyển
    if current_model and normalize_model_name(current_model) == normalized:
        return ModelSwitchResult(
            success=True,
            requested_model=requested_model,
            actual_model=current_model,
            actual_model_normalized=normalized,
        )

    # Quét danh sách model từ UI
    available = await client.get_available_models()

    if not available:
        # Không tìm thấy menu model → dùng model mặc định (không click gì)
        logger.warning("⚠ Không thể quét danh sách model. Sử dụng model mặc định.")
        return ModelSwitchResult(
            success=True,
            requested_model=requested_model,
            actual_model="default",
            actual_model_normalized="gemini-basic",
            fallback=True,
            fallback_reason="Model menu not accessible (possibly free tier)",
        )

    logger.info(f"📋 Models khả dụng: {available}")

    # Thử match model yêu cầu
    matched = match_model_in_list(normalized, available)
    if matched:
        ok = await client.select_model(matched)
        if ok:
            logger.info(f"✓ Đã chọn model: {matched} (yêu cầu: {requested_model})")
            return ModelSwitchResult(
                success=True,
                requested_model=requested_model,
                actual_model=matched,
                actual_model_normalized=normalized,
            )

    # Fallback — thử lần lượt theo thứ tự ưu tiên
    logger.warning(f"⚠ Không tìm thấy '{requested_model}'. Đang thử fallback...")

    for fallback_model in FALLBACK_ORDER:
        if fallback_model == normalized:
            continue  # Đã thử rồi

        fb_matched = match_model_in_list(fallback_model, available)
        if fb_matched:
            ok = await client.select_model(fb_matched)
            if ok:
                logger.info(f"✓ Fallback thành công: {fb_matched} (thay vì {requested_model})")
                return ModelSwitchResult(
                    success=True,
                    requested_model=requested_model,
                    actual_model=fb_matched,
                    actual_model_normalized=fallback_model,
                    fallback=True,
                    fallback_reason=f"'{requested_model}' not available, fell back to '{fb_matched}'",
                )

    # Không match được bất kỳ model nào → dùng mặc định
    logger.warning("⚠ Không match được model nào. Sử dụng model mặc định trên UI.")
    return ModelSwitchResult(
        success=True,
        requested_model=requested_model,
        actual_model="default",
        actual_model_normalized="gemini-basic",
        fallback=True,
        fallback_reason="No matching model found in UI, using default",
    )


def get_all_supported_models() -> list[dict]:
    """Trả về danh sách tất cả models hỗ trợ (cho GET /v1/models)."""
    models = []
    for model_id, ui_names in MODEL_ALIASES.items():
        models.append({
            "id": model_id,
            "aliases": ui_names,
            "description": f"Gemini Web - {', '.join(ui_names)}",
        })
    return models
