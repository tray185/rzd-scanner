# -*- coding: utf-8 -*-
"""
Логика поиска билетов РЖД (без графического интерфейса).
Тот же код, что в десктопной версии — только стандартная библиотека Python.
Используется и приложением на телефоне (Kivy), и десктопной версией.
"""

import json
import os
import ssl
import sys
import time
import tempfile
import urllib.parse
import urllib.request
import urllib.error
import http.cookiejar
from datetime import datetime, timedelta  # noqa: F401  (timedelta удобен наружу)

# ----------------------------- Константы -----------------------------

MONTHS_RU = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
             "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
WEEKDAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

CAR_TYPES = {
    "Любой": None,
    "Плацкарт": "ReservedSeat",
    "Купе": "Compartment",
    "СВ": "Luxury",
    "Люкс (мягкий)": "Soft",
    "Сидячий": "Sedentary",
    "Общий": "Shared",
}

SEAT_TYPES = ["Любое", "Нижнее", "Верхнее", "Нижнее боковое", "Верхнее боковое"]

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Origin": "https://ticket.rzd.ru",
    "Referer": "https://ticket.rzd.ru/",
}

REQUEST_DELAY = 1.5      # пауза между днями, сек (чтобы не забанили)
CAR_REQUEST_DELAY = 1.0  # пауза между запросами состава поездов, сек
REQUEST_TIMEOUT = 30

# На Android системные CA-сертификаты могут быть недоступны urllib —
# берём набор из certifi, если он установлен (в requirements есть).
try:
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    SSL_CTX = ssl.create_default_context()

# Лог отладки — в каталог, куда точно можно писать.
try:
    if getattr(sys, "frozen", False):
        _APP_DIR = os.path.dirname(sys.executable)
    else:
        _APP_DIR = os.path.dirname(os.path.abspath(__file__))
    _test = os.path.join(_APP_DIR, ".wtest")
    with open(_test, "a"):
        pass
    os.remove(_test)
except Exception:
    _APP_DIR = tempfile.gettempdir()
DEBUG_LOG = os.path.join(_APP_DIR, "rzd_debug.log")


def log_debug(text):
    """Пишет строку в rzd_debug.log (ошибки игнорируются)."""
    try:
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (datetime.now().strftime("%d.%m %H:%M:%S"), text))
    except Exception:
        pass


# ----------------------------- API РЖД -----------------------------

_COOKIES = http.cookiejar.CookieJar()
_OPENER = urllib.request.build_opener(
    urllib.request.HTTPSHandler(context=SSL_CTX),
    urllib.request.HTTPCookieProcessor(_COOKIES))
_SESSION_READY = False


def _ensure_session():
    """Один раз заходит на главную, чтобы получить куки сессии."""
    global _SESSION_READY
    if _SESSION_READY:
        return
    try:
        req = urllib.request.Request("https://ticket.rzd.ru/", headers=HEADERS)
        with _OPENER.open(req, timeout=REQUEST_TIMEOUT) as r:
            r.read(1024)
        _SESSION_READY = True
    except Exception as e:
        log_debug("не удалось получить куки сессии: %s" % e)


def http_get_json(url):
    """GET-запрос, возвращает разобранный JSON (читает тело даже при HTTP-ошибке)."""
    _ensure_session()
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with _OPENER.open(req, timeout=REQUEST_TIMEOUT) as r:
            body = r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
    return json.loads(body)


def http_post_json(url, payload):
    """POST JSON, возвращает разобранный JSON (читает тело даже при HTTP-ошибке)."""
    _ensure_session()
    headers = dict(HEADERS)
    headers["Content-Type"] = "application/json"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with _OPENER.open(req, timeout=REQUEST_TIMEOUT) as r:
            body = r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
    return json.loads(body)


def suggest_stations(query):
    """Поиск станций по названию. Возвращает список (название, код экспресс-3)."""
    url = ("https://ticket.rzd.ru/api/v1/suggests?"
           + urllib.parse.urlencode({
               "Query": query,
               "TransportType": "rail",
               "GroupResults": "true",
               "RailwaySortPriority": "true",
               "Language": "ru",
           }))
    data = http_get_json(url)
    result, seen = [], set()
    for key in ("city", "train", "avia", "items"):
        for item in data.get(key) or []:
            code = str(item.get("expressCode") or item.get("nodeId") or "")
            name = item.get("name") or ""
            region = item.get("region") or ""
            if code and code not in seen:
                seen.add(code)
                label = name + ((" (" + region + ")") if region and region != name else "")
                result.append((label, code))
    return result


def fetch_trains(origin_code, dest_code, day, include_disabled=False):
    """Запрос поездов на дату. Возвращает (список поездов, текст ошибки или None)."""
    params = {
        "service_provider": "B2B_RZD",
        "getByLocalTime": "true",
        "carGrouping": "DontGroup",
        "origin": origin_code,
        "destination": dest_code,
        "departureDate": day.strftime("%Y-%m-%d") + "T00:00:00",
    }
    if include_disabled:
        params["specialPlacesDemand"] = "StandardPlacesAndForDisabledPersons"
    url = ("https://ticket.rzd.ru/api/v1/railway-service/prices/train-pricing?"
           + urllib.parse.urlencode(params))
    try:
        data = http_get_json(url)
    except Exception as e:
        log_debug("train-pricing сбой: %s | %s" % (e, url))
        return [], "Ошибка сети: " + str(e)
    if isinstance(data, dict) and data.get("Trains") is not None:
        return data.get("Trains") or [], None
    msg = ""
    if isinstance(data, dict):
        msg = data.get("Message") or data.get("message") or json.dumps(data, ensure_ascii=False)[:200]
    log_debug("train-pricing ошибка: %s | %s" % (msg, url))
    return [], msg or "Неизвестный ответ сервера"


def _uniq(values):
    """Уникальные непустые значения с сохранением порядка."""
    out = []
    for v in values:
        s = str(v).strip() if v is not None else ""
        if s and s not in out:
            out.append(s)
    return out


CAR_PRICING_URL = ("https://ticket.rzd.ru/apib2b/p/Railway/V1/Search/CarPricing"
                   "?service_provider=B2B_RZD&isBonusPurchase=false")


def fetch_cars(origin_code, dest_code, train):
    """Запрос состава поезда (вагоны и конкретные свободные места)."""
    o = str(train.get("OriginStationCode") or origin_code)
    d = str(train.get("DestinationStationCode") or dest_code)
    dep = train.get("DepartureDateTime") or train.get("LocalDepartureDateTime") or ""
    nums = _uniq([train.get("TrainNumber"), train.get("DisplayTrainNumber"),
                  train.get("TrainNumberToGetRoute")])
    if not (o and d and dep and nums):
        return [], "Не хватает данных о поезде в ответе сервера"

    last_msg = "Неизвестный ответ сервера"
    for i, num in enumerate(nums[:2]):
        if i > 0:
            time.sleep(0.7)
        payload = {
            "OriginCode": o,
            "DestinationCode": d,
            "DepartureDate": dep,
            "TrainNumber": num,
            "CarGrouping": "DontGroup",
            "SpecialPlacesDemand": "StandardPlacesAndForDisabledPersons",
        }
        try:
            data = http_post_json(CAR_PRICING_URL, payload)
        except Exception as e:
            last_msg = "Ошибка сети: " + str(e)
            log_debug("CarPricing сбой: %s | %s" % (last_msg, payload))
            continue
        if isinstance(data, dict) and data.get("Cars") is not None:
            return data.get("Cars") or [], None
        if isinstance(data, dict):
            last_msg = (data.get("Message") or data.get("message")
                        or json.dumps(data, ensure_ascii=False)[:300])
        log_debug("CarPricing ошибка: %s | %s | ответ: %s" % (
            last_msg, payload, json.dumps(data, ensure_ascii=False)[:300]
            if isinstance(data, (dict, list)) else str(data)[:300]))
    return [], last_msg


def parse_free_places(free):
    """Разбирает список свободных мест вагона."""
    if free is None:
        return []
    if isinstance(free, str):
        items = free.replace(";", ",").split(",")
    else:
        items = list(free)
    out = []
    for it in items:
        s = str(it).strip()
        digits = ""
        for ch in s:
            if ch.isdigit():
                digits += ch
            else:
                break
        if not digits:
            continue
        out.append((int(digits), s[len(digits):].strip()))
    return out


def classify_place(car_api, num, include_special):
    """Тип места по номеру и типу вагона."""
    def parity(n):
        return "lower" if n % 2 == 1 else "upper"

    if car_api == "Compartment":           # купе: 1-36, спецкупе 37-38
        if num > 36 and not include_special:
            return "special"
        return parity(num)
    if car_api == "ReservedSeat":          # плацкарт: 1-36 осн., 37-54 боковые
        if num > 54 and not include_special:
            return "special"
        if num > 36:
            return "side_lower" if num % 2 == 1 else "side_upper"
        return parity(num)
    if car_api == "Luxury":                # СВ: оба места нижние, 1-18
        if num > 18 and not include_special:
            return "special"
        return "lower"
    if car_api == "Soft":                  # люкс: нижние
        return "lower"
    return "seat"                          # сидячий/общий — без яруса


SEAT_NEED = {
    "Нижнее": {"lower"},
    "Верхнее": {"upper"},
    "Нижнее боковое": {"side_lower"},
    "Верхнее боковое": {"side_upper"},
    "Любое": {"lower", "upper", "side_lower", "side_upper", "seat"},
}


def train_times(train):
    """Строки времени отправления/прибытия для таблицы."""
    dep = train.get("LocalDepartureDateTime") or train.get("DepartureDateTime") or ""
    arr = train.get("LocalArrivalDateTime") or train.get("ArrivalDateTime") or ""
    try:
        dep_s = datetime.fromisoformat(dep).strftime("%d.%m %H:%M")
    except Exception:
        dep_s = dep
    try:
        arr_s = datetime.fromisoformat(arr).strftime("%d.%m %H:%M")
    except Exception:
        arr_s = arr
    return dep_s, arr_s


def filter_by_passengers(rows, n, allow_split):
    """Оставляет только варианты, где хватает мест на n пассажиров."""
    if n <= 1:
        return rows
    if allow_split:
        total = sum(r["seats"] for r in rows)
        return rows if total >= n else []
    by_car = {}
    for r in rows:
        by_car.setdefault(r["carnum"], []).append(r)
    out = []
    for rr in by_car.values():
        if sum(r["seats"] for r in rr) >= n:
            out.extend(rr)
    return out


def train_has_car_type(train, car_api):
    """Быстрая предпроверка по сводке: есть ли вообще такой тип вагона с местами."""
    for grp in train.get("CarGroups") or []:
        if car_api and grp.get("CarType") != car_api:
            continue
        total = int(grp.get("TotalPlaceQuantity") or grp.get("PlaceQuantity") or 0)
        if total > 0:
            return True
    return False


# спецместа, недоступные обычному пассажиру без особых условий
_SPECIAL_MARKERS = ("disabled", "invalid", "инвалид", "сопровожд",
                    "babies", "с детьми", "playground", "игров",
                    "pets", "животн", "mother", "матери и реб")


def place_group_bucket(entry):
    """Тип мест группы по данным сервера (CarPlaceType / CarPlaceNameRu)."""
    pt = str(entry.get("CarPlaceType") or "").lower()
    pn = str(entry.get("CarPlaceNameRu") or "").lower()
    s = pt + "|" + pn
    special = any(k in s for k in _SPECIAL_MARKERS)
    side = ("side" in pt) or ("боков" in pn)
    lower = ("lower" in pt) or ("нижн" in pn)
    upper = ("upper" in pt) or ("верхн" in pn)
    if lower and not upper:
        return ("side_lower" if side else "lower"), special
    if upper and not lower:
        return ("side_upper" if side else "upper"), special
    return None, special


def match_cars(train, cars, car_api, seat_type, include_disabled):
    """Отбирает группы мест нужного типа. Одна строка = одна группа мест."""
    need = set(SEAT_NEED.get(seat_type) or SEAT_NEED["Любое"])
    rows = []
    dep_s, arr_s = train_times(train)
    for car in cars:
        if car_api and car.get("CarType") != car_api:
            continue
        bucket, special = place_group_bucket(car)
        if special and not include_disabled:
            continue
        places = parse_free_places(car.get("FreePlaces"))
        if bucket is not None:
            matched = places if bucket in need else []
            if (matched and not include_disabled
                    and car.get("CarType") == "Compartment"
                    and not car.get("IsTwoStorey")):
                matched = [p for p in matched if p[0] <= 36]
        else:
            two = bool(car.get("IsTwoStorey"))
            matched = []
            for num, sfx in places:
                kind = classify_place(car.get("CarType"), num,
                                      include_disabled or two)
                if kind in need:
                    matched.append((num, sfx))
        if not matched:
            continue
        matched.sort()
        shown = ["%d%s" % (n, sfx) for n, sfx in matched[:14]]
        places_s = ", ".join(shown) + ("…" if len(matched) > 14 else "")
        name = car.get("CarPlaceNameRu") or ""
        if special and name:
            places_s += "  [%s]" % name
        price = car.get("MinPrice") or car.get("MaxPrice")
        price_s = ("{:,.0f} ₽".format(price).replace(",", " ")) if price else "—"
        rows.append({
            "train": train.get("DisplayTrainNumber") or train.get("TrainNumber") or "?",
            "dep": dep_s, "arr": arr_s,
            "car": car.get("CarTypeName") or car.get("CarType") or "?",
            "carnum": str(car.get("CarNumber") or "?"),
            "places": places_s, "seats": len(matched), "price": price_s,
        })
    return rows
