import time
import datetime

def get_timezone() -> str:
    """
    Returns the system timezone name.
    Fallbacks to UTC if not detectable.
    """
    try:
        tz = time.tzname[0]
        if tz:
            return tz
    except Exception:
        pass

    return "UTC"


def now_utc_iso() -> str:
    """
    Returns current UTC time in ISO format.
    Useful for logs and previews.
    """
    return datetime.datetime.utcnow().isoformat() + "Z"
