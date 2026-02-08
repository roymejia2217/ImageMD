import time
from datetime import datetime, timezone

def check_tz():
    print(f"Timezone Name: {time.tzname}")
    print(f"Timezone Offset (seconds): {time.timezone}")
    print(f"Daylight: {time.daylight}")
    
    now = datetime.now()
    ts = now.timestamp()
    
    print(f"Now (Local): {now}")
    print(f"Timestamp: {ts}")
    
    utc_from_ts = datetime.fromtimestamp(ts, timezone.utc)
    print(f"UTC from Timestamp: {utc_from_ts}")
    
    diff = (utc_from_ts.replace(tzinfo=None) - now).total_seconds() / 3600
    print(f"Difference (UTC - Local): {diff} hours")

if __name__ == "__main__":
    check_tz()
