# kern/export_orchestrator.py
from __future__ import annotations

from typing import Dict, Any

# ✅ modularer Export: A4 Trainer
from kern.exports.trainer_a4 import export_trainer_a4


def run_export(mode: str, data: Dict[str, Any], **kwargs) -> bytes:
    """
    Zentrale Weiche für alle Eddie-Module.

    mode:
      - "KDP Buch"
      - "A4 Arbeitsblatt"
      - "QR Lernkarten"

    data (neu, empfohlen):
      {
        "module": "trainer_v2",
        "subject": "...",
        "vocab": [{"word":"...", "translation":"..."}, ...],
        "assets": {"images": [bytes, ...]},
        "options": {...}
      }

    data (legacy, unterstützt):
      {"items":[{"term":..., "icon_slug":..., "examples":..., "note_prompt":...}, ...]}
    """
    if not isinstance(data, dict):
        raise ValueError("run_export: data must be a dict")

    module = str(data.get("module") or "").strip()

    # -----------------------------
    # TRAINER V2 (neues Schema)
    # -----------------------------
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

    # -----------------------------
    # LEGACY: items Payload (dein altes A4 Format)
    # -----------------------------
    if mode == "A4 Arbeitsblatt" and isinstance(data.get("items"), list):
        return _export_a4_legacy_items_via_trainer(data, **kwargs)

    raise ValueError(f"Unsupported export request: module={module!r}, mode={mode!r}")


def _export_a4_legacy_items_via_trainer(data: Dict[str, Any], **kwargs) -> bytes:
    """
    Adapter: hält dein aktuelles items-Format am Leben, aber rendert über export_trainer_a4().

    Hinweis:
    - Legacy 'examples' und 'note_prompt' werden hier NICHT übernommen.
      (Wenn du willst, erweitern wir trainer_a4.py um optionales Rendern dieser Felder.)
    """
    subject = str((data.get("subject") or "")).strip()

    vocab = []
    for it in (data.get("items") or []):
        if not isinstance(it, dict):
            continue
        word = str(it.get("term", "")).strip()
        if word:
            vocab.append({"word": word, "translation": ""})

    bridged: Dict[str, Any] = {
        "module": "trainer_v2",
        "subject": subject,
        "vocab": vocab,
        "assets": {"images": []},
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
