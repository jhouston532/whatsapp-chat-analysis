"""
message.py

Author: WhatsApp Chat Analysis Project

Purpose:
    Defines the core Message data model used throughout the project.

Description:
    Every message parsed from a WhatsApp export is represented as a
    Message object. This module intentionally contains NO parsing,
    analysis, or business logic. It exists solely to define the data
    structure shared between all other modules.

Design Rules:
    - No file I/O
    - No parsing
    - No analysis
    - No helper functions
    - No dependencies on project modules
"""

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Optional


@dataclass(slots=True)
class Message:
    """
    Represents a single message from an exported WhatsApp chat.

    This object is immutable in meaning after creation and serves as the
    common interface between all analysis modules.
    """

    # ------------------------------------------------------------------
    # Original timestamp information
    # ------------------------------------------------------------------

    #: Full timestamp of the message.
    timestamp: datetime

    #: Calendar date extracted from timestamp.
    date: date

    #: Time of day extracted from timestamp.
    time: time

    #: Original timezone label from the export (e.g. "MDT"), if known.
    timezone: Optional[str]

    # ------------------------------------------------------------------
    # Date/time components (stored separately for convenience)
    # ------------------------------------------------------------------

    year: int
    month: int
    day: int

    weekday: int
    """
    Monday = 0
    Tuesday = 1
    ...
    Sunday = 6
    """

    hour: int
    minute: int
    second: int

    # ------------------------------------------------------------------
    # Author information
    # ------------------------------------------------------------------

    #: Cleaned display name or phone number.
    author: str

    #: Original author text exactly as it appeared in the export.
    raw_author: str

    # ------------------------------------------------------------------
    # Message contents
    # ------------------------------------------------------------------

    #: Complete message body.
    message: str

    #: Number of characters in the message body.
    message_length: int

    # ------------------------------------------------------------------
    # Message classification
    # ------------------------------------------------------------------

    #: True if this is a WhatsApp-generated system event.
    is_system_message: bool

    #: True if the message represents omitted media.
    is_media: bool

    # ------------------------------------------------------------------
    # Source information
    # ------------------------------------------------------------------

    #: Line number where the message begins in the exported text file.
    line_number: int
    