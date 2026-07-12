#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import pandas as pd
import re
import time
import urllib3
import os
import json
from datetime import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ===== НАСТРОЙКИ =====
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN', "ВАШ_ТОКЕН")     # замените на ваш токен
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', "ВАШ_CHAT_ID")  # замените на ваш chat_id

ADULTS = 2
PAGE_SIZE = 20
MAX_PAGES = 10
REQUEST_TIMEOUT = 60
RETRY_TOTAL = 3

DATE_DURATION_LIST = [
    ("13.07.2026", 12),
    ("24.07.2026", 11),
    ("03.08.2026", 12),
    ("14.08.2026", 11),
    ("24.08.2026", 12),
    ("04.09.2026", 11),
    ("14.09.2026", 12),
    ("25.09.2026", 11),
    ("05.10.2026", 12),
]
# =====================================

# Получаем путь к папке, где находится скрипт
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PRICES_FILE = os.path.join(SCRIPT_DIR, 'previous_prices.json')

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ===== СЛОВАРЬ СИНОНИМОВ ОТЕЛЕЙ =====
HOTEL_SYNONYMS = {
    "Thapsus Beach Resort": ["THAPSUS BEACH RESORT 4*"],
    "Aziza Thalasso Golf": ["Aziza Beach Thalasso & Golf (Adults Only)", "AZIZA THALASSO GOLF (ADULTS ONLY)"],
    "Iberostar Selection Kuriat Palace": ["Iberostar Kuriat Palace"],
    "Tour Khalef Thalasso and Spa (ex.Jaz)": ["Tour Khalef Thalasso & Spa"],
    "Iberostar Selection Diar El Andalous": ["Iberostar Diar El Andalous"],
    "Iberostar Selection Kantaoui Bay": ["Iberostar Kantaoui Bay"],
    "Steigenberger Marhaba Thalasso Hammamet": ["Steigenberger Marhaba Thalasso"],
    "The Orangers Beach Resort & Bungalows": ["The Orangers Beach Resort & Bungalow"],
    "Iberostar Averroes": ["Iberostar Waves Averroes"],
    "El Mouradi Port Kantaoui": ["El Mouradi Port El Kantaoui"],
    "Novostar Houda Golf & Beach Club": ["Houda Golf Beach & Aquapark"],
    "Thalassa Sousse Resort & Aqua Park": ["Thalassa Sousse Resort & Aquapark"],
    "Regency Hotel & Spa": ["Regency Monastir Hotel & Spa"],
    "Laico Hammamet": ["Blue Marine Hotel & Thalasso (ex. Laico)"],
    "Tunisia Lodge": ["Shell Beach Hotel & Spa (ex. Tunisia Lodge)"],
    "Thalassa Mahdia": ["Thalassa Mahdia Aquapark", "Thalassa Mahdia Aqua Park"],
    "Golden Yasmine Mehari": ["Golden Yasmine Mehari Hammamet Thalasso & Spa", "GOLDEN YASMIN MEHARI HAMMAMET THALASSO & SPA", "Golden Yasmin Mehari  Hammamet", "Golden Yasmine Mehari Hammamet"],
    "Aylimas Beach & Resort": ["Aylimas Beach & Resort (ex.Palmyra Holiday)", "Aylimas Beach & Resort Monastir"],
    "Shems Holiday Village & Aquapark": ["Shems Holiday Village"],
    "TMK L'Atrium Yasmine by Turismark": ["TMK Latrium Yasmine by Turismark", "TMK L'Atrium Yasmine Hammamet"],
    "Monarque El Fatimi & Aquapark": ["Monarque El Fatimi & Aquapark Mahdia", "MONARQUE EL FATIMI & AQUAPARK"],
    "Royal Jinene Beach & Spa": ["Royal Jinene"],
    "Hammamet Hotel & Spa": ["Le Hammamet Hotel & Spa"],
    "Sahara Beach Aquapark Resort": ["Sahara Beach"],
    "Club Novostar Sol Azur Beach Congres": ["Club Novostar Sol Azur Beach Congress"],
    "One Resort Jockey": ["One Resort Jockey (ex. One Resort Monastir)", "One resort Jockey"],
    "Abou Sofiane Hotel & Aquapark": ["Abou Sofiane Hotel"],
    "Calimera El Borj": ["Calimera El Borj Mahdia"],
    "Le Royal Hammamet": ["Le Royal Hotels and Resorts"],
    "Eden Yasmine Resort & Spa": ["Eden Yasmine Resort Meeting & Spa"],
    "Medina Solaria & Thalasso": ["Medina Solaria & Thalasso (ex. Iberostar Solaria)"],
    "Mahdia Beach & Aquapark": ["Mahdia Beach & Aquapark (ex. Lti Mahdia Beach)", "LTI Mahdia Beach & Aquapark"],
    "La Badira (Adults Only)": ["La Badira", "La Badira - Adult Only", "La Badira (adults only)"],
    "Royal Azur Thalassa": ["Royal Azur Thalasso Golf"],
    "Residence Mahmoud": ["RESIDENCE MAHMOUD"]
}

# ===== ФУНКЦИИ ДЛЯ РАБОТЫ С TELEGRAM =====
def send_telegram_message(message):
    """Отправляет сообщение в Telegram, разбивая на части если нужно"""
    try:
        MAX_LENGTH = 4000
        
        if len(message) <= MAX_LENGTH:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {
                'chat_id': TELEGRAM_CHAT_ID,
                'text': message,
                'parse_mode': 'HTML'
            }
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
        
        # Разбиваем на части
        parts = []
        current_part = ""
        for line in message.split('\n'):
            if len(current_part) + len(line) + 1 > MAX_LENGTH:
                parts.append(current_part)
                current_part = line + '\n'
            else:
                current_part += line + '\n'
        if current_part:
            parts.append(current_part)
        
        for i, part in enumerate(parts):
            if len(parts) > 1:
                part = f"📨 Часть {i+1}/{len(parts)}\n\n{part}"
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {
                'chat_id': TELEGRAM_CHAT_ID,
                'text': part,
                'parse_mode': 'HTML'
            }
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code != 200:
                print(f"⚠️ Ошибка отправки части {i+1}: {response.text}")
                return False
            time.sleep(0.5)
        return True
            
    except Exception as e:
        print(f"❌ Ошибка отправки в Telegram: {e}")
        return False

def read_previous_prices():
    """Читает сохранённые цены из файла"""
    try:
        with open(PRICES_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        print(f"ℹ️ Файл {PRICES_FILE} не найден. Начинаем с нуля.")
        return {}

def save_current_prices(prices):
    """Сохраняет текущие цены в файл"""
    try:
        with open(PRICES_FILE, 'w') as f:
            json.dump(prices, f, indent=2)
        print(f"✅ Цены сохранены в {PRICES_FILE}")
    except Exception as e:
        print(f"❌ Ошибка сохранения цен: {e}")

def get_hotel_key(hotel_name, date, duration):
    return f"{hotel_name}_{date}_{duration}"

def compare_prices(old_prices, new_prices):
    """
    Сравнивает старые и новые цены.
    Поддерживает два формата old_prices:
    1. Новый: {key: {operator: price}}
    2. Старый: {key: price} (для обратной совместимости)
    """
    changes = []
    
    for key, new_data in new_prices.items():
        old_data = old_prices.get(key)
        
        # Разбираем ключ: "Отель_дата_длительность"
        parts = key.rsplit('_', 2)
        if len(parts) == 3:
            hotel_name = parts[0]
            date_str = parts[1]
            duration = parts[2]
        else:
            hotel_name = key
            date_str = "неизвестно"
            duration = "?"
        
        # Проверяем, старый это формат или новый
        if isinstance(old_data, dict):
            # Новый формат: {operator: price}
            for operator, new_price in new_data.items():
                old_price = old_data.get(operator)
                if old_price is None:
                    changes.append(f"🆕 {operator}: {hotel_name} ({date_str}, {duration}д): ${new_price:.0f}")
                elif abs(new_price - old_price) > 0.01:
                    diff = new_price - old_price
                    icon = "⬆️" if diff > 0 else "⬇️"
                    changes.append(
                        f"{icon} {operator}: {hotel_name} ({date_str}, {duration}д): "
                        f"${old_price:.0f} → ${new_price:.0f} ({'+' if diff > 0 else ''}{diff:.0f})"
                    )
        else:
            # Старый формат: просто число (для обратной совместимости)
            # Берём первую цену из new_data (обычно это Intercity)
            first_operator = next(iter(new_data.keys()))
            new_price = new_data[first_operator]
            old_price = old_data
            
            if old_price is None:
                changes.append(f"🆕 {first_operator}: {hotel_name} ({date_str}, {duration}д): ${new_price:.0f}")
            elif abs(new_price - old_price) > 0.01:
                diff = new_price - old_price
                icon = "⬆️" if diff > 0 else "⬇️"
                changes.append(
                    f"{icon} {first_operator}: {hotel_name} ({date_str}, {duration}д): "
                    f"${old_price:.0f} → ${new_price:.0f} ({'+' if diff > 0 else ''}{diff:.0f})"
                )
    
    return changes

# ===== ФУНКЦИИ ПАРСИНГА =====
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

    tour_name = tour.get('Name', '')
    room_category = None
    partner_name = None

    for service in tour.get('Services', []):
        if 'Hotel' in service and 'HotelDetails' in service:
            details = service['HotelDetails']
            if details and isinstance(details, list):
                min_cost = None
                best_detail = None
                for detail in details:
                    cost = detail.get('Cost', 0)
                    if min_cost is None or cost < min_cost:
                        min_cost = cost
                        best_detail = detail
                if best_detail:
                    if 'RoomCategory' in best_detail and 'Value' in best_detail['RoomCategory']:
                        room_category = best_detail['RoomCategory']['Value']
                    partner = best_detail.get('Partner')
                    if partner and isinstance(partner, dict) and 'Value' in partner:
                        partner_name = partner['Value']
            if not partner_name:
                hotel = service.get('Hotel')
                if hotel and 'Partner' in hotel and isinstance(hotel['Partner'], dict):
                    partner_name = hotel['Partner'].get('Value')
            if not partner_name:
                if 'Partner' in service and isinstance(service['Partner'], dict):
                    partner_name = service['Partner'].get('Value')
            break

    return hotel_name, price, tour_name, room_category, partner_name

def fetch_all_pages(url, params_template, source_name, verify_ssl=True, timeout=REQUEST_TIMEOUT):
    all_hotels = {}
    page = 1
    total_tours = 0
    print(f"\n📡 Загружаем {source_name}...")

    session = requests.Session()
    retries = Retry(total=RETRY_TOTAL, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    session.mount('https://', HTTPAdapter(max_retries=retries))
    session.mount('http://', HTTPAdapter(max_retries=retries))

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'application/json, text/plain, */*',
    }

    while page <= MAX_PAGES:
        params = params_template.copy()
        params['PageNumber'] = page
        params['_'] = int(time.time() * 1000)
        if 'SearchId' in params:
            params['SearchId'] = page

        try:
            print(f"  Страница {page}...", end=" ")
            r = session.get(url, params=params, headers=headers, timeout=timeout, verify=verify_ssl)
            if r.status_code == 200:
                data = r.json()
                tours = data.get('Result', [])
                if not tours:
                    print("нет данных")
                    break
                print(f"{len(tours)} туров")
                total_tours += len(tours)
                for tour in tours:
                    original_name, price, tour_name, room_category, partner = extract_hotel_info(tour)
                    if original_name and price > 0:
                        canonical = get_canonical_name(original_name)
                        key = normalize_hotel_name(canonical)
                        if key in all_hotels:
                            if price < all_hotels[key]['price']:
                                all_hotels[key] = {
                                    'original_name': canonical,
                                    'price': price,
                                    'tour_name': tour_name,
                                    'room_category': room_category,
                                    'partner': partner
                                }
                        else:
                            all_hotels[key] = {
                                'original_name': canonical,
                                'price': price,
                                'tour_name': tour_name,
                                'room_category': room_category,
                                'partner': partner
                            }
                if len(tours) < PAGE_SIZE:
                    break
                page += 1
                time.sleep(0.5)
            else:
                print(f"Ошибка HTTP {r.status_code}")
                break
        except requests.exceptions.Timeout:
            print(f"Таймаут на странице {page}. Повторяем...")
            time.sleep(2)
            continue
        except Exception as e:
            print(f"Ошибка: {e}")
            break

    print(f"  ✅ Уникальных отелей: {len(all_hotels)}")
    return all_hotels

# ----- Источники данных -----
def get_intercity_hotels(date, duration):
    url = "https://api75.intercity.by:9000/TourSearchOwin2/Tour"
    params = {
        'DepartureCityKeys': 448,
        'Dates': date,
        'Durations': duration,
        'PageSize': PAGE_SIZE,
        'HotelScheme': '',
        'TourKey': '',
        'TourDuration': '',
        'ShowToursWithoutHotels': -1,
        'isFromBasket': 'false',
        'isFillSecondaryFilters': 'false',
        'DestinationType': 1,
        'DestinationKey': 97,
        'AdultCount': ADULTS,
        'CurrencyName': '$',
        'AviaQuota': 5,
        'HotelQuota': 7,
        'BusTransferQuota': 7,
        'RailwayTransferQuota': 7,
        'TourType': -1,
        'CityIds': -1,
        'HotelSignCombination': 'false',
        'HotelCombination': 'false',
        'TimeDepartureFrom': '00:00',
        'TimeDepartureTo': '23:59',
        'TimeArrivalFrom': '00:00',
        'TimeArrivalTo': '23:59',
        'SearchId': 3,
        'wrongLicenseFileUpperTitle': 'Некорректный файл лицензии.',
        'RemoteHotelMode': 0,
    }
    return fetch_all_pages(url, params, "Intercity", verify_ssl=False, timeout=90)

def get_rosting_hotels(date, duration):
    url = "https://online.rosting.by:9000/TourSearchOwin/Tour"
    params = {
        'DepartureCityKeys': 448,
        'Dates': date,
        'Durations': duration,
        'PageSize': PAGE_SIZE,
        'HotelScheme': '', 'TourKey': '', 'TourDuration': '',
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
    return fetch_all_pages(url, params, "Rosting")

def get_tv_hotels(date, duration):
    url = "https://booking.t-v.by:9001/TourSearchOwin/Tour"
    params = {
        'DepartureCityKeys': 448,
        'Dates': date,
        'Durations': duration,
        'PageSize': PAGE_SIZE,
        'HotelScheme': '', 'TourKey': '', 'TourDuration': '',
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
    return fetch_all_pages(url, params, "T-V")

def get_voyage_hotels(date, duration):
    url = "https://b2b.tovtour.by:57127/TourSearch/Tour"
    params = {
        'DepartureCityKeys': 448,
        'Dates': date,
        'Durations': duration,
        'PageSize': PAGE_SIZE,
        'HotelScheme': '', 'TourKey': '', 'TourDuration': '',
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
    return fetch_all_pages(url, params, "Voyage", verify_ssl=False)

def get_abs_hotels(date, duration):
    url = "https://on.abstour.by:2340/TourSearchOwin/Tour"
    params = {
        'DepartureCityKeys': 448,
        'Dates': date,
        'Durations': duration,
        'PageSize': PAGE_SIZE,
        'HotelScheme': '', 'TourKey': '', 'TourDuration': '',
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
    return fetch_all_pages(url, params, "ABS", verify_ssl=False)

# ===== ОСНОВНАЯ ФУНКЦИЯ =====
def main():
    print("="*70)
    print("🏨 МОНИТОРИНГ ЦЕН ТУРОВ ТУНИС")
    print("="*70)
    print(f"📅 Время запуска: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📁 Файл с ценами: {PRICES_FILE}")

    today = datetime.now().date()
    current_prices = {}

    for date_str, duration in DATE_DURATION_LIST:
        try:
            date_obj = datetime.strptime(date_str, "%d.%m.%Y").date()
        except ValueError:
            continue
        if date_obj < today:
            continue

        print(f"\n📅 Обработка даты: {date_str}, {duration} дней")
        print("-" * 40)

        source_functions = {
            'Intercity': get_intercity_hotels,
            'Rosting': get_rosting_hotels,
            'T-V': get_tv_hotels,
            'Voyage': get_voyage_hotels,
            'ABS': get_abs_hotels,
        }

        all_prices = {}
        for name, func in source_functions.items():
            result = func(date_str, duration)
            for key, data in result.items():
                hotel_key = get_hotel_key(data['original_name'], date_str, duration)
                if hotel_key not in all_prices:
                    all_prices[hotel_key] = {}
                # Сохраняем цену для этого оператора
                all_prices[hotel_key][name] = data['price']

        current_prices.update(all_prices)

    # Сравниваем с предыдущими ценами
    previous_prices = read_previous_prices()
    changes = compare_prices(previous_prices, current_prices)

    # Сохраняем текущие цены
    save_current_prices(current_prices)

    # Формируем и отправляем сообщение
    if changes:
        up = sum(1 for c in changes if '⬆️' in c)
        down = sum(1 for c in changes if '⬇️' in c)
        new = sum(1 for c in changes if '🆕' in c)
        
        message = f"🔔 <b>ИЗМЕНЕНИЯ ЦЕН</b>\n"
        message += f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        message += f"📊 Всего изменений: {len(changes)}\n"
        message += f"🆕 Новые отели: {new}\n"
        message += f"⬆️ Повысилось: {up}\n"
        message += f"⬇️ Понизилось: {down}\n"
        
        if len(changes) > 15:
            message += f"\n📋 Первые 15 изменений:\n"
            message += "\n".join(changes[:15])
            message += f"\n\n... и ещё {len(changes) - 15} изменений."
        else:
            message += f"\n📋 Список изменений:\n"
            message += "\n".join(changes)
        
        send_telegram_message(message)
        print(f"📨 Отправлено уведомление в Telegram ({len(changes)} изменений)")
    else:
        # Отправляем уведомление, что изменений нет
        message = f"✅ <b>ЦЕНЫ НЕ ИЗМЕНИЛИСЬ</b>\n"
        message += f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        message += f"📊 Всего отелей в мониторинге: {len(current_prices)}\n"
        message += f"🔄 Следующая проверка через 30 минут"
        
        send_telegram_message(message)
        print(f"📨 Отправлено уведомление в Telegram (изменений нет)")

if __name__ == "__main__":
    main()