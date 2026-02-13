# kern/export_orchestrator.py
from __future__ import annotations

from typing import Dict, Any

# Exporter
from kern.exports.trainer_a4 import export_trainer_a4


def run_export(mode: str, data: Dict[str, Any], **kwargs) -> bytes:
    """
    Zentrale Weiche für alle Eddie-Module.
    - mode: "KDP Buch" | "A4 Arbeitsblatt" | "QR Lernkarten"
    - data: standardisiertes Payload (module, subject, vocab, assets, options)
    """
    module = (data or {}).get("module", "") or ""

    # --- Trainer V2 ---
    if module == "trainer_v2":
        if mode == "A4 Arbeitsblatt":
            return export_trainer_a4(
                data,
                title=kwargs.get("title", "Eddie Trainer V2"),
                subtitle=kwargs.get("subtitle"),
                watermark=kwargs.get("watermark", True),
                lines=kwargs.get("lines", True),
                policy=kwargs.get("policy"),
            )
        if mode == "KDP Buch":
            raise NotImplementedError("Trainer KDP Export noch nicht verdrahtet.")
        if mode == "QR Lernkarten":
            raise NotImplementedError("Trainer Cards Export noch nicht verdrahtet.")

    # --- Legacy: items payload (dein altes A4-Format) ---
    # Damit du nicht alles auf einmal migrieren musst.
    if mode == "A4 Arbeitsblatt" and isinstance((data or {}).get("items"), list):
        return _export_a4_legacy_items(data, **kwargs)

    raise ValueError(f"Unsupported export request: module={module!r}, mode={mode!r}")


# ----------------------------
# Legacy Adapter (optional)
# ----------------------------
def _export_a4_legacy_items(data: Dict[str, Any], **kwargs) -> bytes:
    """
    Übergangslösung:
    Konvertiert data["items"] -> trainer_v2 Schema und nutzt export_trainer_a4.
    items: [{term, icon_slug, examples, note_prompt}, ...]
    """
    subject = (data or {}).get("subject", "") or ""

    items = (data or {}).get("items") or []
    vocab = []
    for it in items:
        if not isinstance(it, dict):
            continue
        vocab.append(
            {
                "word": str(it.get("term", "")).strip(),
                "translation": "",  # legacy
            }
        )

    bridged = {
        "module": "trainer_v2",
        "subject": str(subject).strip(),
        "vocab": vocab,
        "assets": {"images": []},  # legacy hat hier keine images-bytes
        "options": {
            "writing_lines_per_page": 5,
        },
    }

    return export_trainer_a4(
        bridged,
        title=kwargs.get("title", "Eddie – Arbeitsblatt"),
        subtitle=kwargs.get("subtitle"),
        watermark=kwargs.get("watermark", True),
        lines=kwargs.get("lines", True),
        policy=kwargs.get("policy"),
    )
