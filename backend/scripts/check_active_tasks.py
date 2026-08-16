import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.celery_app import celery_app

def main():
    insp = celery_app.control.inspect(timeout=2.0)
    active = insp.active()

    if not active:
        print("Aktif görev yok.")
        return 0

    total = 0
    for worker_name, tasks in active.items():
        for t in tasks:
            total += 1
            print(f"  - [{worker_name}] {t.get('name')} (id={t.get('id')})")

    if total == 0:
        print("Aktif görev yok.")
        return 0

    print(f"UYARI: {total} aktif görev var.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
