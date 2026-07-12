#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import pandas as pd
import re
import time
import urllib3
import os
import json
import sys
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ===== НАСТРОЙКИ (через переменные окружения) =====
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', "ВАШ_ТОКЕН")
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', "ВАШ_CHAT_ID")

ADULTS = 2
PAGE_SIZE = 20
MAX_PAGES = 3
REQUEST_TIMEOUT = 30
RETRY_TOTAL = 2

DATE_DURATION_LIST = [
    ("13.07.2026", 12),
]
# =====================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PRICES_FILE = os.path.join(SCRIPT_DIR, 'previous_prices.json')

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def flush_print(*args, **kwargs):
    print(*args, **kwargs)
    sys.stdout.flush()

# ===== СЛОВАРЬ СИНОНИМОВ ОТЕЛЕЙ (сокращённый) =====
HOTEL_SYNONYMS = {
    "Residence Mahmoud": ["RESIDENCE MAHMOUD"],
    "Best Beach Hotel": ["Best Beach Hotel"],
}

def get_canonical_name(original_name):
    if not original_name:
        return ""
    def clean(s):
        return re.sub(r'\s+', ' ', s.lower().strip())
    cleaned = clean(original_name)
    for canonical, variants in HOTEL_SYNONYMS.items():
        for variant in variants:
            if clean(variant) == cleaned:
                return canonical
    return original_name.strip()

def normalize_hotel_name(name):
    if not name:
        return ""
    name = str(name).lower()
    name = re.sub(r'[^\w\s\-\.]', ' ', name)
    name = re.sub(r'\s+', ' ', name).strip()
    stop_words = ['отель', 'hotel', 'resort', '&', 'and', 'spa', 'thalasso', 'club', 'premium']
    for word in stop_words:
        name = re.sub(rf'\b{word}\b', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\s+', ' ', name).strip()
    return name

def extract_hotel_info(tour):
    price = tour.get('Price', 0)
    if not price or price == 0:
        return None, 0, None, None, None

    hotel_name = None
    for service in tour.get('Services', []):
        if 'Hotel' in service and 'Value' in service.get('Hotel', {}):
            hotel_name = service['Hotel']['Value']
            break
    return hotel_name, price, tour.get('Name', ''), None, None

def send_telegram_message(message):
    try:
        flush_print("📨 Отправка в Telegram...")
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'HTML'
        }
        response = requests.post(url, json=payload, timeout=10)
        flush_print(f"📨 Ответ Telegram: {response.status_code}")
        return response.status_code == 200
    except Exception as e:
        flush_print(f"❌ Ошибка отправки в Telegram: {e}")
        return False

def read_previous_prices():
    try:
        with open(PRICES_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_current_prices(prices):
    try:
        with open(PRICES_FILE, 'w') as f:
            json.dump(prices, f, indent=2)
        flush_print(f"✅ Цены сохранены в {PRICES_FILE}")
    except Exception as e:
        flush_print(f"❌ Ошибка сохранения цен: {e}")

def get_hotel_key(hotel_name, date, duration):
    return f"{hotel_name}_{date}_{duration}"

def compare_prices(old_prices, new_prices):
    changes = []
    for key, new_data in new_prices.items():
        old_data = old_prices.get(key, {})
        parts = key.rsplit('_', 2)
        if len(parts) == 3:
            hotel_name = parts[0]
            date_str = parts[1]
            duration = parts[2]
        else:
            hotel_name = key
            date_str = "неизвестно"
            duration = "?"
        
        for operator, new_price in new_data.items():
            old_price = old_data.get(operator)
            if old_price is None:
                changes.append(f"🆕 {operator}: {hotel_name} ({date_str}, {duration}д): ${new_price:.0f}")
            elif abs(new_price - old_price) > 0.01:
                diff = new_price - old_price
                icon = "⬆️" if diff > 0 else "⬇️"
                changes.append(f"{icon} {operator}: {hotel_name} ({date_str}, {duration}д): ${old_price:.0f} → ${new_price:.0f}")
    return changes

def fetch_all_pages(url, params_template, source_name, verify_ssl=True, timeout=REQUEST_TIMEOUT):
    flush_print(f"\n📡 ЗАГРУЖАЕМ {source_name}...")
    flush_print(f"   URL: {url}")
    flush_print(f"   Таймаут: {timeout} сек")
    
    all_hotels = {}
    page = 1
    total_tours = 0

    session = requests.Session()
    retries = Retry(total=RETRY_TOTAL, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session.mount('https://', HTTPAdapter(max_retries=retries))
    session.mount('http://', HTTPAdapter(max_retries=retries))

    # --- ЗАГОЛОВКИ КАК В БРАУЗЕРЕ ---
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'Referer': 'https://on.abstour.by/',
        'Origin': 'https://on.abstour.by',
    }

    while page <= MAX_PAGES:
        params = params_template.copy()
        params['PageNumber'] = page
        params['_'] = int(time.time() * 1000)
        if 'SearchId' in params:
            params['SearchId'] = page

        try:
            flush_print(f"  Страница {page}...", end="")
            r = session.get(url, params=params, headers=headers, timeout=timeout, verify=verify_ssl)
            flush_print(f" статус {r.status_code}")
            
            if r.status_code == 200:
                data = r.json()
                tours = data.get('Result', [])
                if not tours:
                    flush_print("  ❌ нет данных (пустой Result)")
                    break
                flush_print(f"  ✅ {len(tours)} туров")
                total_tours += len(tours)
                for tour in tours:
                    original_name, price, _, _, _ = extract_hotel_info(tour)
                    if original_name and price > 0:
                        canonical = get_canonical_name(original_name)
                        key = normalize_hotel_name(canonical)
                        if key in all_hotels:
                            if price < all_hotels[key]['price']:
                                all_hotels[key] = {'original_name': canonical, 'price': price}
                        else:
                            all_hotels[key] = {'original_name': canonical, 'price': price}
                if len(tours) < PAGE_SIZE:
                    flush_print("  📄 последняя страница")
                    break
                page += 1
                time.sleep(0.3)
            else:
                flush_print(f"  ❌ Ошибка HTTP {r.status_code}")
                break
        except requests.exceptions.Timeout:
            flush_print(f"  ⏰ Таймаут на странице {page}.")
            flush_print(f"  🔄 Пропускаем {source_name} (таймаут)")
            break
        except Exception as e:
            flush_print(f"  ❌ Ошибка: {e}")
            break

    flush_print(f"  ✅ Уникальных отелей: {len(all_hotels)}")
    return all_hotels

# ----- 1. Intercity -----
def get_intercity_hotels(date, duration):
    url = "https://api75.intercity.by:9000/TourSearchOwin2/Tour"
    params = {
        'DepartureCityKeys': 448, 'Dates': date, 'Durations': duration,
        'PageSize': PAGE_SIZE, 'HotelScheme': '', 'TourKey': '', 'TourDuration': '',
        'ShowToursWithoutHotels': -1, 'isFromBasket': 'false', 'isFillSecondaryFilters': 'false',
        'DestinationType': 1, 'DestinationKey': 97, 'AdultCount': ADULTS,
        'CurrencyName': '$', 'AviaQuota': 5, 'HotelQuota': 7, 'BusTransferQuota': 7,
        'RailwayTransferQuota': 7, 'TourType': -1, 'CityIds': -1,
        'HotelSignCombination': 'false', 'HotelCombination': 'false',
        'TimeDepartureFrom': '00:00', 'TimeDepartureTo': '23:59',
        'TimeArrivalFrom': '00:00', 'TimeArrivalTo': '23:59',
        'SearchId': 3, 'wrongLicenseFileUpperTitle': 'Некорректный файл лицензии.',
        'RemoteHotelMode': 0,
    }
    return fetch_all_pages(url, params, "Intercity", verify_ssl=False, timeout=90)

# ----- 2. Rosting -----
def get_rosting_hotels(date, duration):
    url = "https://online.rosting.by:9000/TourSearchOwin/Tour"
    params = {
        'DepartureCityKeys': 448, 'Dates': date, 'Durations': duration,
        'PageSize': PAGE_SIZE, 'HotelScheme': '', 'TourKey': '', 'TourDuration': '',
        'ShowToursWithoutHotels': -1, 'isFromBasket': 'false', 'isFillSecondaryFilters': 'false',
        'DestinationType': 1, 'DestinationKey': 97, 'AdultCount': ADULTS,
        'CurrencyName': '$', 'AviaQuota': 7, 'HotelQuota': 5, 'BusTransferQuota': 5,
        'RailwayTransferQuota': 7, 'TourType': 383, 'CityIds': -1,
        'HotelSignCombination': 'false', 'HotelCombination': 'false',
        'TimeDepartureFrom': '00:00', 'TimeDepartureTo': '23:59',
        'TimeArrivalFrom': '00:00', 'TimeArrivalTo': '23:59',
        'SearchId': 1, 'wrongLicenseFileUpperTitle': 'Некорректный файл лицензии.',
        'RemoteHotelMode': 0,
    }
    return fetch_all_pages(url, params, "Rosting", timeout=REQUEST_TIMEOUT)

# ----- 3. T-V -----
def get_tv_hotels(date, duration):
    url = "https://booking.t-v.by:9001/TourSearchOwin/Tour"
    params = {
        'DepartureCityKeys': 448, 'Dates': date, 'Durations': duration,
        'PageSize': PAGE_SIZE, 'HotelScheme': '', 'TourKey': '', 'TourDuration': '',
        'ShowToursWithoutHotels': -1, 'isFromBasket': 'false', 'isFillSecondaryFilters': 'false',
        'DestinationType': 1, 'DestinationKey': 97, 'AdultCount': ADULTS,
        'CurrencyName': '$', 'AviaQuota': 5, 'HotelQuota': 7, 'BusTransferQuota': 7,
        'RailwayTransferQuota': 7, 'TourType': -1, 'CityIds': -1,
        'HotelSignCombination': 'false', 'HotelCombination': 'false',
        'TimeDepartureFrom': '00:00', 'TimeDepartureTo': '23:59',
        'TimeArrivalFrom': '00:00', 'TimeArrivalTo': '23:59',
        'SearchId': 1, 'wrongLicenseFileUpperTitle': 'Некорректный файл лицензии.',
        'RemoteHotelMode': 0,
    }
    return fetch_all_pages(url, params, "T-V", timeout=REQUEST_TIMEOUT)

# ----- 4. Voyage -----
def get_voyage_hotels(date, duration):
    url = "https://b2b.tovtour.by:57127/TourSearch/Tour"
    params = {
        'DepartureCityKeys': 448, 'Dates': date, 'Durations': duration,
        'PageSize': PAGE_SIZE, 'HotelScheme': '', 'TourKey': '', 'TourDuration': '',
        'ShowToursWithoutHotels': -1, 'isFromBasket': 'false', 'isFillSecondaryFilters': 'false',
        'DestinationType': 1, 'DestinationKey': 97, 'AdultCount': ADULTS,
        'CurrencyName': '$', 'AviaQuota': 5, 'HotelQuota': 7, 'BusTransferQuota': 7,
        'RailwayTransferQuota': 7, 'TourType': 1266, 'CityIds': -1,
        'HotelSignCombination': 'false', 'HotelCombination': 'false',
        'TimeDepartureFrom': '00:00', 'TimeDepartureTo': '23:59',
        'TimeArrivalFrom': '00:00', 'TimeArrivalTo': '23:59',
        'SearchId': 1, 'wrongLicenseFileUpperTitle': 'Некорректный файл лицензии.',
        'RemoteHotelMode': 0,
    }
    return fetch_all_pages(url, params, "Voyage", verify_ssl=False, timeout=REQUEST_TIMEOUT)

# ----- 5. ABS -----
def get_abs_hotels(date, duration):
    url = "https://on.abstour.by:2340/TourSearchOwin/Tour"
    params = {
        'DepartureCityKeys': 448, 'Dates': date, 'Durations': duration,
        'PageSize': PAGE_SIZE, 'HotelScheme': '', 'TourKey': '', 'TourDuration': '',
        'ShowToursWithoutHotels': -1, 'isFromBasket': 'false', 'isFillSecondaryFilters': 'false',
        'DestinationType': 1, 'DestinationKey': 97, 'AdultCount': ADULTS,
        'CurrencyName': '$', 'AviaQuota': 5, 'HotelQuota': 5, 'BusTransferQuota': 7,
        'RailwayTransferQuota': 7, 'TourType': -1, 'CityIds': -1,
        'HotelSignCombination': 'false', 'HotelCombination': 'false',
        'TimeDepartureFrom': '00:00', 'TimeDepartureTo': '23:59',
        'TimeArrivalFrom': '00:00', 'TimeArrivalTo': '23:59',
        'SearchId': 4, 'wrongLicenseFileUpperTitle': 'Некорректный файл лицензии.',
        'RemoteHotelMode': 0,
    }
    return fetch_all_pages(url, params, "ABS", verify_ssl=False, timeout=60)

# ===== ОСНОВНАЯ ФУНКЦИЯ =====
def main():
    flush_print("="*70)
    flush_print("🏨 МОНИТОРИНГ ЦЕН (ТЕСТОВЫЙ РЕЖИМ)")
    flush_print("="*70)
    flush_print(f"📅 Время запуска: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    flush_print(f"📁 Файл с ценами: {PRICES_FILE}")
    flush_print(f"📡 Python version: {sys.version}")

    today = datetime.now().date()
    current_prices = {}

    for date_str, duration in DATE_DURATION_LIST:
        try:
            date_obj = datetime.strptime(date_str, "%d.%m.%Y").date()
        except ValueError:
            continue
        if date_obj < today:
            continue

        flush_print(f"\n📅 Обработка даты: {date_str}, {duration} дней")
        flush_print("-" * 40)

        source_functions = {
            'Intercity': get_intercity_hotels,
            'Rosting': get_rosting_hotels,
            'T-V': get_tv_hotels,
            'Voyage': get_voyage_hotels,
            'ABS': get_abs_hotels,
        }

        for name, func in source_functions.items():
            flush_print(f"\n🔄 Загрузка {name}...")
            try:
                result = func(date_str, duration)
                flush_print(f"   ✅ Загружено {len(result)} отелей")
                for key, data in result.items():
                    hotel_key = get_hotel_key(data['original_name'], date_str, duration)
                    if hotel_key not in current_prices:
                        current_prices[hotel_key] = {}
                    current_prices[hotel_key][name] = data['price']
            except Exception as e:
                flush_print(f"   ❌ Ошибка при загрузке {name}: {e}")

    flush_print(f"\n📊 Всего отелей: {len(current_prices)}")

    flush_print("\n📨 Отправляем тестовое сообщение...")
    test_message = f"✅ <b>ТЕСТОВОЕ СООБЩЕНИЕ</b>\n"
    test_message += f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    test_message += f"📊 Найдено отелей: {len(current_prices)}\n"
    
    operators_count = {}
    for hotel_data in current_prices.values():
        for op in hotel_data.keys():
            operators_count[op] = operators_count.get(op, 0) + 1
    
    test_message += f"\n📊 По источникам:\n"
    for op, count in sorted(operators_count.items()):
        test_message += f"   {op}: {count} отелей\n"
    
    test_message += f"\n🔄 Скрипт работает в GitHub Actions!"
    
    send_telegram_message(test_message)
    flush_print("✅ ТЕСТ ЗАВЕРШЁН!")

if __name__ == "__main__":
    main()