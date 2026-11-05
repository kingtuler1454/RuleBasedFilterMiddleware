import argparse
import random
import time
import uuid
from collections import Counter
from dataclasses import dataclass

import requests


@dataclass
class RunStats:
    total: int = 0
    ok: int = 0
    forbidden: int = 0
    errors: int = 0
    status_codes: Counter = None

    def __post_init__(self):
        if self.status_codes is None:
            self.status_codes = Counter()

    def add(self, code: int):
        self.total += 1
        self.status_codes[code] += 1
        if code == 200:
            self.ok += 1
        elif code == 403:
            self.forbidden += 1
        elif code >= 400:
            self.errors += 1


def clamp(v, lo, hi):
    return max(lo, min(v, hi))


def z_max_index(z: int) -> int:
    return (2 ** z) - 1


def sleep_jitter(short_min=0.03, short_max=0.25, long_p=0.08, long_min=0.4, long_max=1.6):
    if random.random() < long_p:
        time.sleep(random.uniform(long_min, long_max))
    else:
        time.sleep(random.uniform(short_min, short_max))


def request_tile(base_url: str, z: int, x: int, y: int, session_id: str, timeout=10, retries=2) -> int:
    params = {"z": z, "x": x, "y": y, "sessionId": session_id}
    last_code = 599
    for _ in range(retries + 1):
        try:
            r = requests.get(base_url, params=params, timeout=timeout)
            return r.status_code
        except requests.RequestException:
            last_code = 598
            time.sleep(0.2)
    return last_code


def iter_grid(z, x0, x1, y0, y1, reverse=False):
    xs = range(x0, x1 + 1)
    ys = range(y0, y1 + 1)
    if reverse:
        xs = reversed(list(xs))
        ys = reversed(list(ys))
    for x in xs:
        for y in ys:
            yield z, x, y


def iter_random_unique(z, x0, x1, y0, y1, limit):
    coords = [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]
    random.shuffle(coords)
    for x, y in coords[: min(limit, len(coords))]:
        yield z, x, y


def iter_burst(z, x0, x1, y0, y1, limit):
    # burst: пачки быстрых запросов + прыжки по области
    cx = random.randint(x0, x1)
    cy = random.randint(y0, y1)
    produced = 0
    while produced < limit:
        burst_len = random.randint(8, 25)
        for _ in range(burst_len):
            if produced >= limit:
                break
            dx, dy = random.choice([(1, 0), (-1, 0), (0, 1), (0, -1), (0, 0), (2, 0), (0, 2), (-2, 0), (0, -2)])
            cx = clamp(cx + dx, x0, x1)
            cy = clamp(cy + dy, y0, y1)
            produced += 1
            yield z, cx, cy
        # редкий дальний прыжок
        cx = random.randint(x0, x1)
        cy = random.randint(y0, y1)


def iter_human_like_pan(z, x0, x1, y0, y1, limit):
    # ближе к человеку: соседние тайлы и паузы
    cx = random.randint(x0, x1)
    cy = random.randint(y0, y1)
    for _ in range(limit):
        yield z, cx, cy
        dx, dy = random.choice([(1, 0), (-1, 0), (0, 1), (0, -1), (0, 0), (1, 1), (-1, -1)])
        cx = clamp(cx + dx, x0, x1)
        cy = clamp(cy + dy, y0, y1)


def run(mode, base_url, z, x0, x1, y0, y1, limit, session_id):
    stats = RunStats()

    if mode == "grid":
        gen = iter_grid(z, x0, x1, y0, y1, reverse=False)
        delay = (0.02, 0.08, 0.02, 0.25, 0.7)
    elif mode == "grid_reverse":
        gen = iter_grid(z, x0, x1, y0, y1, reverse=True)
        delay = (0.02, 0.08, 0.02, 0.25, 0.7)
    elif mode == "random_unique":
        gen = iter_random_unique(z, x0, x1, y0, y1, limit)
        delay = (0.03, 0.12, 0.04, 0.3, 1.0)
    elif mode == "burst":
        gen = iter_burst(z, x0, x1, y0, y1, limit)
        delay = (0.005, 0.03, 0.15, 0.4, 1.2)
    else:
        gen = iter_human_like_pan(z, x0, x1, y0, y1, limit)
        delay = (0.05, 0.25, 0.1, 0.5, 1.8)

    print(f"sessionId={session_id}")
    print(f"mode={mode}, z={z}, bbox=({x0}:{x1},{y0}:{y1}), limit={limit}")

    sent = 0
    for zz, xx, yy in gen:
        if mode in ("grid", "grid_reverse") and sent >= limit:
            break
        code = request_tile(base_url, zz, xx, yy, session_id)
        stats.add(code)
        sent += 1
        if sent % 50 == 0:
            print(f"sent={sent} last={zz},{xx},{yy} code={code}")
        sleep_jitter(*delay)

    print("\n=== RUN STATS ===")
    print(f"total={stats.total}, ok={stats.ok}, forbidden={stats.forbidden}, errors={stats.errors}")
    print("codes:", dict(stats.status_codes))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:5279/Tiles")
    parser.add_argument("--mode", choices=["grid", "grid_reverse", "random_unique", "burst", "human_like_pan"], default="burst")
    parser.add_argument("--z", type=int, default=6)
    parser.add_argument("--x0", type=int, default=0)
    parser.add_argument("--x1", type=int, default=200)
    parser.add_argument("--y0", type=int, default=0)
    parser.add_argument("--y1", type=int, default=200)
    parser.add_argument("--limit", type=int, default=800)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--session", default="")
    args = parser.parse_args()

    random.seed(args.seed)

    zmax = z_max_index(args.z)
    x0 = clamp(min(args.x0, args.x1), 0, zmax)
    x1 = clamp(max(args.x0, args.x1), 0, zmax)
    y0 = clamp(min(args.y0, args.y1), 0, zmax)
    y1 = clamp(max(args.y0, args.y1), 0, zmax)

    if x0 == x1 and y0 == y1:
        raise SystemExit("Слишком узкая область (1 тайл). Увеличьте bbox.")

    session_id = args.session or str(uuid.uuid4())
    run(args.mode, args.url, args.z, x0, x1, y0, y1, args.limit, session_id)


if __name__ == "__main__":
    main()