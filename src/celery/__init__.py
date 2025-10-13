"""
Celery integration for sending match data to RabbitMQ queue.
"""

from .queue_client import MatchQueueClient

__all__ = ["MatchQueueClient"]
