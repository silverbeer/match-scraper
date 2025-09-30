"""
API integration modules for external services.

This package provides clients for integrating with external APIs,
including the missing-table.com service for match data management.
"""

from .missing_table_client import MissingTableClient

__all__ = ["MissingTableClient"]
