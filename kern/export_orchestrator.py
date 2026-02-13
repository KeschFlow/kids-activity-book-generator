# kern/export_orchestrator.py
from __future__ import annotations

from typing import Dict, Any

from kern.exports.trainer_a4 import export_trainer_a4
from kern.exports.trainer_cards import export_trainer_cards


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

        if mode == "QR Lernkarten":
            return export_trainer_cards(
                data,
                title=kwargs.get("title", "Eddie – QR Lernkarten"),
                subtitle=kwargs.get("subtitle"),
                watermark=kwargs.get("watermark", True),
                policy=kwargs.get("policy"),
            )

        if mode == "KDP Buch":
            raise NotImplementedError("Trainer KDP Export noch nicht verdrahtet.")

    # -----------------------------
    # LEGACY: items Payload (altes A4 Format)
    # -----------------------------
    if mode == "A4 Arbeitsblatt" and isinstance(data.get("items"), list):
        return _export_a4_legacy_items_via_trainer(data, **kwargs)

    # Optional: Legacy -> Cards (wenn du das willst, aktivieren)
    if mode == "QR Lernkarten" and isinstance(data.get("items"), list):
        return _export_cards_legacy_items_via_trainer(data, **kwargs)

    raise ValueError(f"Unsupported export request: module={module!r}, mode={mode!r}")


def _export_a4_legacy_items_via_trainer(data: Dict[str, Any], **kwargs) -> bytes:
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
        # Wir lassen items drin, damit trainer_a4.py legacy examples/note_prompt nutzen kann
        "items": data.get("items"),
    }

    return export_trainer_a4(
        bridged,
        title=kwargs.get("title", "Eddie – Arbeitsblatt"),
        subtitle=kwargs.get("subtitle"),
        watermark=kwargs.get("watermark", True),
        lines=kwargs.get("lines", True),
        policy=kwargs.get("policy"),
    )


def _export_cards_legacy_items_via_trainer(data: Dict[str, Any], **kwargs) -> bytes:
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
        "options": {},
        # items drin lassen, damit trainer_cards.py legacy examples/icon_slug nutzen kann
        "items": data.get("items"),
    }

    return export_trainer_cards(
        bridged,
        title=kwargs.get("title", "Eddie – QR Lernkarten"),
        subtitle=kwargs.get("subtitle"),
        watermark=kwargs.get("watermark", True),
        policy=kwargs.get("policy"),
    )
