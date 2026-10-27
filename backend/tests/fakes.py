"""Testlerde kullanılan küçük sahte altyapı nesneleri (Redis ve IMAP gelen kutusu)."""


class FakeLock:
    def __init__(self, store, name):
        self._store = store
        self._name = name
        self.extended = 0

    def acquire(self, blocking=True):
        if self._name in self._store.locks:
            return False
        self._store.locks.add(self._name)
        return True

    def extend(self, additional_time, replace_ttl=False):
        self.extended += 1

    def release(self):
        self._store.locks.discard(self._name)


class FakeRedis:
    """redis_client'ın kullanılan alt kümesi: set/get/exists/incr/expire/delete/lock."""

    def __init__(self):
        self.data: dict[str, str] = {}
        self.ttl: dict[str, int] = {}
        self.locks: set[str] = set()

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.data:
            return None
        self.data[key] = str(value)
        if ex is not None:
            self.ttl[key] = ex
        return True

    def get(self, key):
        return self.data.get(key)

    def exists(self, key):
        return 1 if key in self.data else 0

    def incr(self, key):
        self.data[key] = str(int(self.data.get(key, "0")) + 1)
        return int(self.data[key])

    def expire(self, key, seconds):
        self.ttl[key] = seconds
        return True

    def delete(self, key):
        self.data.pop(key, None)
        self.ttl.pop(key, None)

    def lock(self, name, timeout=None, blocking=True):
        return FakeLock(self, name)


class FakeInbox:
    """ImapInbox'ın görev tarafından kullanılan alt kümesi; mesajlar {uid: ham_bytes} olarak verilir."""

    def __init__(self, messages: dict[int, bytes]):
        self.messages = messages
        self.uidvalidity = 7
        self.marked: dict[int, bool] = {}  # uid -> flagged mi
        self.full_fetches: list[int] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def list_unseen_uids(self):
        return sorted(self.messages)

    def fetch_headers(self, uids):
        return {uid: self.messages[uid].split(b"\r\n\r\n", 1)[0] + b"\r\n\r\n" for uid in uids}

    def fetch_message(self, uid):
        self.full_fetches.append(uid)
        return self.messages[uid]

    def synthetic_message_id(self, uid):
        return f"<imap-{self.uidvalidity}-{uid}@ik-asistan.local>"

    def mark_processed(self, uid, flagged=False):
        self.marked[uid] = flagged
