# -*- coding: utf-8 -*-
"""
Сканер билетов РЖД — версия для Android (KivyMD).
Интерфейс адаптирован под вертикальный экран смартфона.
Логика поиска — в rzd_core.py (общая с десктопной версией).
"""

import threading
import time
from datetime import date, timedelta

from kivy.clock import Clock, mainthread
from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView

from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDRaisedButton, MDFlatButton, MDIconButton
from kivymd.uix.textfield import MDTextField
from kivymd.uix.selectioncontrol import MDCheckbox
from kivymd.uix.menu import MDDropdownMenu
from kivymd.uix.pickers import MDDatePicker
from kivymd.uix.progressbar import MDProgressBar
from kivymd.uix.bottomnavigation import MDBottomNavigation, MDBottomNavigationItem
from kivymd.uix.list import MDList
from kivymd.uix.dialog import MDDialog

import rzd_core as core


def toast(text):
    """Короткое сообщение (snackbar)."""
    try:
        from kivymd.uix.snackbar import Snackbar
        Snackbar(text=text).open()
    except Exception:
        print(text)


class RowField(MDBoxLayout):
    """Поле-кнопка с подписью, открывает выпадающее меню по нажатию."""
    pass


class RZDApp(MDApp):

    def build(self):
        self.title = "Сканер билетов РЖД"
        self.theme_cls.primary_palette = "Red"
        self.theme_cls.primary_hue = "700"
        self.theme_cls.material_style = "M3"

        # состояние
        self.origin = None        # (название, код)
        self.dest = None
        self.date_from = date.today() + timedelta(days=1)
        self.date_to = date.today() + timedelta(days=7)
        self.car_type = "Купе"
        self.seat_type = "Нижнее"
        self.pax = 1
        self.allow_split = False
        self.include_disabled = False

        self._stop = threading.Event()
        self._scan_thread = None
        self._menu = None
        self._date_target = None
        self._origin_results = []
        self._dest_results = []

        self.nav = MDBottomNavigation()
        self.nav.add_widget(self._build_search_tab())
        self.nav.add_widget(self._build_results_tab())
        return self.nav

    # ----------------- Вкладка «Поиск» -----------------

    def _section(self, text):
        return MDLabel(text=text, font_style="Overline",
                       theme_text_color="Primary",
                       adaptive_height=True, padding=(0, dp(6)))

    def _build_search_tab(self):
        tab = MDBottomNavigationItem(name="search", text="Поиск",
                                     icon="magnify")
        scroll = ScrollView()
        box = MDBoxLayout(orientation="vertical", adaptive_height=True,
                          padding=dp(14), spacing=dp(6),
                          size_hint_y=None)
        box.bind(minimum_height=box.setter("height"))

        # --- станции ---
        box.add_widget(self._section("МАРШРУТ"))

        self.origin_field = MDTextField(hint_text="Откуда", text="Санкт-Петербург")
        row_o = MDBoxLayout(adaptive_height=True, spacing=dp(8))
        row_o.add_widget(self.origin_field)
        row_o.add_widget(MDRaisedButton(text="Найти",
                         on_release=lambda *a: self._search_station("origin")))
        box.add_widget(row_o)
        self.origin_label = MDLabel(text="Станция не выбрана",
                                    theme_text_color="Hint",
                                    adaptive_height=True, font_style="Caption")
        box.add_widget(self.origin_label)

        self.dest_field = MDTextField(hint_text="Куда", text="Волгодонск")
        row_d = MDBoxLayout(adaptive_height=True, spacing=dp(8))
        row_d.add_widget(self.dest_field)
        row_d.add_widget(MDRaisedButton(text="Найти",
                         on_release=lambda *a: self._search_station("dest")))
        box.add_widget(row_d)
        self.dest_label = MDLabel(text="Станция не выбрана",
                                  theme_text_color="Hint",
                                  adaptive_height=True, font_style="Caption")
        box.add_widget(self.dest_label)

        # --- даты ---
        box.add_widget(self._section("ДАТЫ"))
        self.btn_from = MDRaisedButton(
            text="С: " + self.date_from.strftime("%d.%m.%Y"),
            on_release=lambda *a: self._open_date("from"))
        self.btn_to = MDRaisedButton(
            text="По: " + self.date_to.strftime("%d.%m.%Y"),
            on_release=lambda *a: self._open_date("to"))
        drow = MDBoxLayout(adaptive_height=True, spacing=dp(8))
        drow.add_widget(self.btn_from)
        drow.add_widget(self.btn_to)
        box.add_widget(drow)

        # --- параметры вагона/места ---
        box.add_widget(self._section("ВАГОН И МЕСТО"))
        self.btn_car = MDRaisedButton(
            text="Вагон: " + self.car_type,
            on_release=lambda *a: self._open_choice(
                self.btn_car, list(core.CAR_TYPES.keys()), self._set_car))
        box.add_widget(self.btn_car)
        self.btn_seat = MDRaisedButton(
            text="Место: " + self.seat_type,
            on_release=lambda *a: self._open_choice(
                self.btn_seat, core.SEAT_TYPES, self._set_seat))
        box.add_widget(self.btn_seat)

        # --- пассажиры ---
        box.add_widget(self._section("ПАССАЖИРЫ"))
        prow = MDBoxLayout(adaptive_height=True, spacing=dp(6))
        prow.add_widget(MDIconButton(icon="minus-circle-outline",
                                     on_release=lambda *a: self._chg_pax(-1)))
        self.pax_label = MDLabel(text="1", halign="center",
                                 adaptive_height=True, font_style="H6")
        prow.add_widget(self.pax_label)
        prow.add_widget(MDIconButton(icon="plus-circle-outline",
                                     on_release=lambda *a: self._chg_pax(1)))
        box.add_widget(prow)

        self.split_cb = self._checkbox_row(
            box, "Можно в разных вагонах", "allow_split")
        self.disabled_cb = self._checkbox_row(
            box, "Включая спецместа (инвалиды, с детьми…)", "include_disabled")

        # --- кнопки запуска ---
        box.add_widget(self._section(""))
        self.scan_btn = MDRaisedButton(
            text="Начать сканирование", pos_hint={"center_x": 0.5},
            on_release=lambda *a: self.start_scan())
        box.add_widget(self.scan_btn)
        self.stop_btn = MDFlatButton(
            text="Остановить", pos_hint={"center_x": 0.5}, disabled=True,
            on_release=lambda *a: self.stop_scan())
        box.add_widget(self.stop_btn)

        self.progress = MDProgressBar(value=0, max=1)
        box.add_widget(self.progress)
        self.status_label = MDLabel(
            text="Найдите станции кнопкой «Найти».",
            adaptive_height=True, font_style="Caption",
            theme_text_color="Secondary")
        box.add_widget(self.status_label)

        scroll.add_widget(box)
        tab.add_widget(scroll)
        return tab

    def _checkbox_row(self, parent, text, attr):
        row = MDBoxLayout(adaptive_height=True, spacing=dp(6))
        cb = MDCheckbox(size_hint=(None, None), size=(dp(40), dp(40)))

        def on_active(inst, value, a=attr):
            setattr(self, a, value)
        cb.bind(active=on_active)
        row.add_widget(cb)
        row.add_widget(MDLabel(text=text, adaptive_height=True,
                               font_style="Body2"))
        parent.add_widget(row)
        return cb

    # ----------------- Вкладка «Результаты» -----------------

    def _build_results_tab(self):
        tab = MDBottomNavigationItem(name="results", text="Результаты",
                                     icon="format-list-bulleted")
        root = MDBoxLayout(orientation="vertical")
        self.summary_label = MDLabel(
            text="Результаты появятся здесь после сканирования.",
            adaptive_height=True, padding=(dp(14), dp(10)),
            font_style="Subtitle2", theme_text_color="Primary")
        root.add_widget(self.summary_label)
        scroll = ScrollView()
        self.results_list = MDList()
        scroll.add_widget(self.results_list)
        root.add_widget(scroll)
        tab.add_widget(root)
        return tab

    # ----------------- Выпадающие меню / даты -----------------

    def _open_choice(self, caller, options, on_pick):
        items = [{
            "text": opt,
            "viewclass": "OneLineListItem",
            "height": dp(48),
            "on_release": lambda x=opt: self._pick_choice(x, on_pick),
        } for opt in options]
        self._menu = MDDropdownMenu(caller=caller, items=items, width_mult=4)
        self._menu.open()

    def _pick_choice(self, value, on_pick):
        if self._menu:
            self._menu.dismiss()
        on_pick(value)

    def _set_car(self, value):
        self.car_type = value
        self.btn_car.text = "Вагон: " + value

    def _set_seat(self, value):
        self.seat_type = value
        self.btn_seat.text = "Место: " + value

    def _chg_pax(self, delta):
        self.pax = max(1, min(10, self.pax + delta))
        self.pax_label.text = str(self.pax)

    def _open_date(self, which):
        self._date_target = which
        cur = self.date_from if which == "from" else self.date_to
        picker = MDDatePicker(min_date=date.today(),
                              year=cur.year, month=cur.month, day=cur.day)
        picker.bind(on_save=self._on_date_save)
        picker.open()

    def _on_date_save(self, instance, value, date_range):
        if self._date_target == "from":
            self.date_from = value
            self.btn_from.text = "С: " + value.strftime("%d.%m.%Y")
        else:
            self.date_to = value
            self.btn_to.text = "По: " + value.strftime("%d.%m.%Y")

    # ----------------- Поиск станций -----------------

    def _search_station(self, which):
        field = self.origin_field if which == "origin" else self.dest_field
        q = (field.text or "").strip()
        if len(q) < 2:
            toast("Введите минимум 2 символа названия станции")
            return
        toast("Поиск станций…")
        threading.Thread(target=self._search_station_thread,
                         args=(which, q), daemon=True).start()

    def _search_station_thread(self, which, q):
        try:
            found = core.suggest_stations(q)
        except Exception as e:
            self._station_error(str(e))
            return
        self._station_done(which, found)

    @mainthread
    def _station_error(self, err):
        self._dialog("Поиск станции", "Не удалось выполнить поиск:\n" + err)

    @mainthread
    def _station_done(self, which, found):
        if not found:
            self._dialog("Поиск станции",
                         "Станции не найдены. Уточните название.")
            return
        caller = self.origin_field if which == "origin" else self.dest_field
        items = [{
            "text": "%s  [%s]" % (n, c),
            "viewclass": "OneLineListItem",
            "height": dp(48),
            "on_release": lambda nn=n, cc=c: self._pick_station(which, nn, cc),
        } for n, c in found]
        self._menu = MDDropdownMenu(caller=caller, items=items, width_mult=5)
        self._menu.open()

    def _pick_station(self, which, name, code):
        if self._menu:
            self._menu.dismiss()
        if which == "origin":
            self.origin = (name, code)
            self.origin_label.text = "✓ " + name
            self.origin_label.theme_text_color = "Primary"
        else:
            self.dest = (name, code)
            self.dest_label.text = "✓ " + name
            self.dest_label.theme_text_color = "Primary"

    # ----------------- Запуск сканирования -----------------

    def start_scan(self):
        if not self.origin or not self.dest:
            self._dialog("Станции не выбраны",
                         "Сначала найдите и выберите станции отправления и "
                         "прибытия (кнопка «Найти»).")
            return
        if self.date_to < self.date_from:
            self._dialog("Даты", "Дата «по» раньше даты «с».")
            return
        if self.date_from < date.today():
            self._dialog("Даты", "Начальная дата уже в прошлом.")
            return
        n_days = (self.date_to - self.date_from).days + 1
        if n_days > 90:
            self._dialog("Даты", "Слишком большой диапазон (максимум 90 дней).")
            return

        self.results_list.clear_widgets()
        self.summary_label.text = "Идёт сканирование…"
        self.progress.max = n_days
        self.progress.value = 0
        self._stop.clear()
        self.scan_btn.disabled = True
        self.stop_btn.disabled = False

        args = (self.origin, self.dest, self.date_from, n_days,
                core.CAR_TYPES[self.car_type], self.seat_type,
                self.include_disabled, max(1, self.pax), self.allow_split)
        self._scan_thread = threading.Thread(target=self._scan, args=args,
                                             daemon=True)
        self._scan_thread.start()

    def stop_scan(self):
        self._stop.set()
        self._set_status("Останавливаю…")

    def _scan(self, origin, dest, d_from, n_days, car_api, seat_type,
              include_disabled, pax, allow_split):
        ok_days, err_days = [], []
        for i in range(n_days):
            if self._stop.is_set():
                break
            day = d_from + timedelta(days=i)
            self._set_status("Проверяю %s…" % day.strftime("%d.%m.%Y"))
            self._set_progress(i)
            trains, err = core.fetch_trains(origin[1], dest[1], day,
                                            include_disabled)
            if err and not trains:
                err_days.append((day, err))
            rows = []
            for tr in trains:
                if self._stop.is_set():
                    break
                if not core.train_has_car_type(tr, car_api):
                    continue
                time.sleep(core.CAR_REQUEST_DELAY)
                num = tr.get("DisplayTrainNumber") or tr.get("TrainNumber") or "?"
                self._set_status("Проверяю %s, поезд %s…"
                                 % (day.strftime("%d.%m.%Y"), num))
                cars, cerr = core.fetch_cars(origin[1], dest[1], tr)
                if cerr:
                    err_days.append((day, "поезд %s: %s" % (num, cerr)))
                    continue
                trows = core.match_cars(tr, cars, car_api, seat_type,
                                        include_disabled)
                rows.extend(core.filter_by_passengers(trows, pax, allow_split))
            if rows:
                ok_days.append(day)
                self._add_rows(day, rows)
            if i < n_days - 1 and not self._stop.is_set():
                time.sleep(core.REQUEST_DELAY)
        self._scan_done(ok_days, err_days, n_days)

    # ----------------- Обновление UI (главный поток) -----------------

    @mainthread
    def _set_status(self, text):
        self.status_label.text = text

    @mainthread
    def _set_progress(self, value):
        self.progress.value = value

    @mainthread
    def _add_rows(self, day, rows):
        for r in rows:
            self.results_list.add_widget(self._result_card(day, r))

    def _result_card(self, day, r):
        card = MDCard(orientation="vertical", padding=dp(10),
                      spacing=dp(2), size_hint_y=None, height=dp(120),
                      radius=[dp(10)], elevation=1,
                      md_bg_color=(0.91, 0.97, 0.91, 1))
        head = "%s · поезд %s · %s" % (day.strftime("%d.%m"), r["train"], r["car"])
        card.add_widget(MDLabel(text=head, font_style="Subtitle2",
                                adaptive_height=True))
        card.add_widget(MDLabel(
            text="Отпр. %s → Приб. %s · вагон №%s" % (r["dep"], r["arr"], r["carnum"]),
            font_style="Caption", theme_text_color="Secondary",
            adaptive_height=True))
        card.add_widget(MDLabel(
            text="Места: %s" % r["places"], font_style="Body2",
            adaptive_height=True))
        card.add_widget(MDLabel(
            text="Кол-во: %d · Цена от: %s" % (r["seats"], r["price"]),
            font_style="Caption", theme_text_color="Primary",
            adaptive_height=True))
        return card

    @mainthread
    def _scan_done(self, ok_days, err_days, n_days):
        self.scan_btn.disabled = False
        self.stop_btn.disabled = True
        self.progress.value = self.progress.max
        stopped = self._stop.is_set()
        if ok_days:
            days_s = ", ".join(d.strftime("%d.%m") for d in ok_days)
            self.summary_label.text = "Места есть в дни (%d): %s" % (
                len(ok_days), days_s)
        else:
            self.summary_label.text = ("По заданным критериям мест не найдено."
                                       if not stopped else "Сканирование остановлено.")
        msg = "Готово: проверено дней — %d, с местами — %d." % (
            n_days if not stopped else int(self.progress.value), len(ok_days))
        if err_days:
            first = err_days[0]
            msg += "  Ошибок: %d (напр. %s: %s)" % (
                len(err_days), first[0].strftime("%d.%m"), first[1][:60])
        self.status_label.text = msg
        if ok_days:
            toast("Готово! Откройте вкладку «Результаты».")

    # ----------------- Диалог -----------------

    def _dialog(self, title, text):
        d = MDDialog(title=title, text=text,
                     buttons=[MDFlatButton(text="OK")])
        d.buttons[0].bind(on_release=lambda *a: d.dismiss())
        d.open()


if __name__ == "__main__":
    RZDApp().run()
