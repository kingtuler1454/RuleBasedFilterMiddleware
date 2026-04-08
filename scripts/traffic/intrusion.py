import random
import time
import uuid

import requests

tile_server_url = "http://localhost:5279/Tiles"


def sleep_human(short_pause_prob: float = 0.85) -> None:
    """Пауза между запросами: обычно короткая, иногда длинная (как у человека)."""
    if random.random() < short_pause_prob:
        time.sleep(random.uniform(0.04, 0.35))
    else:
        time.sleep(random.uniform(0.4, 2.2))


def fetch_tile(z: int, x: int, y: int, session_id) -> int:
    params = {"z": z, "x": x, "y": y, "sessionId": str(session_id)}
    r = requests.get(tile_server_url, params=params, timeout=30)
    return r.status_code


def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def human_like_pan(
    zoom: int,
    left_x: int,
    right_x: int,
    upper_y: int,
    lower_y: int,
    steps: int,
    session_id,
) -> None:
    """
    Имитация панорамирования: случайное блуждание по соседним тайлам с отражением от границ.
    Один фиксированный z — без скачков масштаба
    """
    if left_x > right_x or upper_y > lower_y:
        raise ValueError("Неверные границы: нужно left_x <= right_x и upper_y <= lower_y")

    max_index = 2**zoom - 1
    left_x, right_x = clamp(left_x, 0, max_index), clamp(right_x, 0, max_index)
    upper_y, lower_y = clamp(upper_y, 0, max_index), clamp(lower_y, 0, max_index)

    cx = random.randint(left_x, right_x)
    cy = random.randint(upper_y, lower_y)
    z = zoom

    for _ in range(steps):
        cx = clamp(cx, left_x, right_x)
        cy = clamp(cy, upper_y, lower_y)

        code = fetch_tile(z, cx, cy, session_id)
        print(z, cx, cy, code)
        sleep_human()

        dx, dy = random.choice([(1, 0), (-1, 0), (0, 1), (0, -1), (0, 0), (1, 1), (-1, -1)])
        cx = clamp(cx + dx, left_x, right_x)
        cy = clamp(cy + dy, upper_y, lower_y)


def random_bulk_download(
    zoom: int,
    left_x: int,
    right_x: int,
    upper_y: int,
    lower_y: int,
    *,
    unique_tiles: int | None = None,
    with_delays: bool = True,
    session_id=None,
) -> None:
    """
    Случайные тайлы в прямоугольнике 
    unique_tiles — сколько уникальных пар (x,y) запросить (по умолчанию — площадь прямоугольника).
    """
    session_id = session_id or uuid.uuid4()
    if left_x > right_x or upper_y > lower_y:
        raise ValueError("Неверные границы: нужно left_x <= right_x и upper_y <= lower_y")

    max_index = 2**zoom - 1
    left_x, right_x = clamp(left_x, 0, max_index), clamp(right_x, 0, max_index)
    upper_y, lower_y = clamp(upper_y, 0, max_index), clamp(lower_y, 0, max_index)

    width = right_x - left_x + 1
    height = lower_y - upper_y + 1
    cap = width * height
    n = cap if unique_tiles is None else min(unique_tiles, cap)

    seen: set[tuple[int, int]] = set()
    while len(seen) < n:
        x = random.randint(left_x, right_x)
        y = random.randint(upper_y, lower_y)
        if (x, y) in seen:
            continue
        seen.add((x, y))
        code = fetch_tile(zoom, x, y, session_id)
        print(zoom, x, y, code)
        if with_delays:
            sleep_human()


def basic_bulk_download(z: int, session_id) -> None:
    """Полный перебор сетки z=z """
    for x in range(0, 2**z):
        for y in range(0, 2**z):
            code = fetch_tile(z, x, y, session_id)
            print(z, x, y, code)


def basic_bulk_download_reverse(z: int, session_id) -> None:
    for x in range(2**z - 1, -1, -1):
        for y in range(2**z - 1, -1, -1):
            code = fetch_tile(z, x, y, session_id)
            print(z, x, y, code)


if __name__ == "__main__":
    session_id = uuid.uuid5(uuid.NAMESPACE_DNS, "human_like_pan_session")
    print(session_id)

    # # Имитация пользователя: маленькое окно + блуждание + паузы
    human_like_pan(
        zoom=2,
        left_x=0,
        right_x=2,
        upper_y=0,
        lower_y=2,
        steps=120,
        session_id=session_id,
    )

    # Более «робот», но с задержками (для контраста в датасете):
    random_bulk_download(2, 0, 2, 1, 3, unique_tiles=80, with_delays=True, session_id=uuid.uuid4())

    # Агрессивный grid (только для маленького z):
    #basic_bulk_download(2,session_id)
