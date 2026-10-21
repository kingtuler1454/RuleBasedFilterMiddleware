import requests
import time
import random
import uuid

BASE_URL = "http://78.17.115.9/Tiles"

def download_tile(z, x, y, session_id):
    url = f"{BASE_URL}?z={z}&x={x}&y={y}&sessionId={session_id}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        return response.status_code == 200
    except Exception:
        return False

def run_for_duration(duration_min, mode_func, mode_name):
    print(f"Запуск {mode_name} ({duration_min} мин)...")
    end_time = time.time() + (duration_min * 60)
    mode_func(end_time)
    print(f"{mode_name} завершен.")

def mode_mass_download(end_time):
    """Тупой бот: качает всё подряд, но иногда прыгает"""
    z_level = 10
    session_id = str(uuid.uuid4())
    while time.time() < end_time:
        for x in range(2**z_level):
            for y in range(2**z_level):
                if time.time() >= end_time: return
                download_tile(z_level, x, y, session_id)
                # Случайная задержка от 0.01 до 0.1 сек
                time.sleep(random.uniform(0.01, 0.1))

def mode_random_scan(end_time):
    """Умный бот: случайно прыгает по всей карте с рандомными задержками"""
    session_id = str(uuid.uuid4())
    while time.time() < end_time:
        z = random.randint(0, 15)
        x = random.randint(0, 2**z - 1)
        y = random.randint(0, 2**z - 1)
        download_tile(z, x, y, session_id)
        # Пауза от 0.5 до 3 секунд, чтобы имитировать человека
        time.sleep(random.uniform(0.5, 3.0))

def mode_smart_pan(end_time):
    """Продвинутый бот: ходит по карте, но делает хаотичные движения"""
    z_level = 12
    x = 2**(z_level - 1)
    y = 2**(z_level - 1)
    session_id = str(uuid.uuid4())
    while time.time() < end_time:
        download_tile(z_level, x, y, session_id)
        
        # В 70% случаев двигаемся на 1 тайл, в 30% - прыгаем на 2-3
        step = 1 if random.random() < 0.7 else random.randint(2, 3)
        
        direction = random.choice(['up', 'down', 'left', 'right'])
        if direction == 'up': y = max(0, y - step)
        elif direction == 'down': y = min(2**z_level - 1, y + step)
        elif direction == 'left': x = max(0, x - step)
        elif direction == 'right': x = min(2**z_level - 1, x + step)
        
        # Рандомная пауза (иногда быстро, иногда долго)
        if random.random() < 0.2:
            time.sleep(random.uniform(2.0, 5.0)) # "Задумался"
        else:
            time.sleep(random.uniform(0.1, 0.8)) # "Быстро крутит"

if __name__ == "__main__":
    DURATION = 10
    run_for_duration(DURATION, mode_mass_download, "Массовое")
    run_for_duration(DURATION, mode_smart_pan, "Умный")
    run_for_duration(DURATION, mode_random_scan, "Случайный")