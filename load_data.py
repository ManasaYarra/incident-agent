import time
from memory import save_incident
from fake_data import fake_incidents

saved = 0
for i, inc in enumerate(fake_incidents, start=1):
    try:
        save_incident(
            inc["log"],
            inc["root_cause"],
            inc["fix"],
            inc["outcome"],
        )
        saved += 1
        print(f"[{i}/{len(fake_incidents)}] Saved: {inc['log'][:50]!r}")
        time.sleep(1)
    except Exception as e:
        print(f"[{i}/{len(fake_incidents)}] FAILED: {e!r}")

print(f"Done. Saved {saved} of {len(fake_incidents)} incidents.")