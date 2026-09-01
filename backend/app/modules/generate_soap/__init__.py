"""SOAP generation via the Aava documentation agent."""

from app.modules.generate_soap.agent_call import generate_soap_note
from app.modules.generate_soap.parse import parse_soap_markdown

__all__ = ["generate_soap_note", "parse_soap_markdown"]
