import time, pytz
import datetime

def get_timezone() -> str:
    """
    Returns the system timezone name.
    Fallbacks to UTC if not detectable.
    """
    try:
        if(time.tzname[0] == 'IST'):
            tz = pytz.timezone("Asia/Kolkata")
        else:
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
