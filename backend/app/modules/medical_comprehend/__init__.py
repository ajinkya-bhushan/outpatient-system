"""AWS Comprehend Medical entity extraction.

Refactored from soap_create/app.py so a transcript can be passed in instead of
a hardcoded sample conversation.
"""

from app.modules.medical_comprehend.app import (
    build_aava_payload,
    detect_entities,
    infer_icd10,
    infer_rx_norm,
    summarize_entities,
)

__all__ = [
    "build_aava_payload",
    "detect_entities",
    "infer_icd10",
    "infer_rx_norm",
    "summarize_entities",
]
