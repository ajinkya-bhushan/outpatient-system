"""AWS Comprehend Medical entity extraction.

Refactored from soap_create/app.py so a transcript can be passed in instead of
a hardcoded sample conversation.
"""

from app.modules.medical_comprehend.app import detect_entities, summarize_entities

__all__ = ["detect_entities", "summarize_entities"]
