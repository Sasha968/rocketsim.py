# ============================================================
#  RocketSim — симулятор ракет на чистом Python + tkinter
#  Автор: Саша
#  Никаких внешних библиотек не требуется
# ============================================================

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import math
import json
import os
import time
import random

# ==================== КОНСТАНТЫ ====================
WIDTH = 1100
HEIGHT = 700
FPS = 30
FRAME_TIME = 1000 // FPS

# Физика
GRAVITY = 9.81
DRAG_COEFF = 0.0008
ATMOSPHERE_HEIGHT = 100000
KARMAN_LINE = 100000

# Цвета
COLORS = {
    "bg": "#0a0a1e",
    "sky_low": "#64aae6",
    "sky_high": "#050514",
    "ground": "#463728",
    "rocket": "#e6e6f0",
    "nose": "#c83232",
    "tank": "#b4b4c8",
    "engine": "#5a5a64",
    "flame": "#ffa01e",
    "flame_core": "#ffff96",
    "ui_bg": "#141928",
    "ui_text": "#e6e6f0",
    "ui_accent": "#50b4ff",
    "ui_warn": "#ff6464",
    "ui_ok": "#64e678",
    "star": "#ffffff",
}


# ==================== ДЕТАЛИ РАКЕТЫ ====================
class Part:
    """Базовая деталь"""
    def __init__(self, name, mass, height, width, color, part_type):
        self.name = name
        self.mass = mass
        self.height = height
        self.width = width
        self.color = color
        self.part_type = part_type
        self.fuel = 0.0
        self.max_fuel = 0.0
        self.thrust = 0.0
        self.fuel_rate = 0.0
        self.active = True
        self.alive = True

    @property
    def total_mass(self):
        return self.mass + self.fuel

    def clone(self):
        p = Part(self.name, self.mass, self.height, self.width, self.color, self.part_type)
        p.fuel = self.fuel
        p.max_fuel = self.max_fuel
        p.thrust = self.thrust
        p.fuel_rate = self.fuel_rate
        return p


class NoseCone(Part):
    def __init__(self, name="Обтекатель", mass=50, height=2.0, width=1.2):
        super().__init__(name, mass, height, width, COLORS["nose"], "nose")


class FuelTank(Part):
    def __init__(self, name="Бак", mass=200, fuel=2000, height=4.0, width=1.2):
        super().__init__(name, mass, height, width, COLORS["tank"], "tank")
        self.fuel = fuel
        self.max_fuel = fuel


class Engine(Part):
    def __init__(self, name="Двигатель", mass=300, thrust=25000, fuel_rate=15, height=2.5, width=1.4):
        super().__init__(name, mass, height, width, COLORS["engine"], "engine")
        self.thrust = thrust
        self.fuel_rate = fuel_rate


# ==================== КАТАЛОГ ДЕТАЛЕЙ ====================
PARTS_CATALOG = {
    "noses": [
        NoseCone("Обтекатель МК-1", 50, 2.0, 1.2),
        NoseCone("Обтекатель МК-2", 80, 2.5, 1.5),
    ],
    "tanks": [
        FuelTank("Бак Т-100", 200, 2000, 4.0, 1.2),
        FuelTank("Бак Т-200", 350, 4000, 5.0, 1.4),
        FuelTank("Бак Т-500", 800, 10000, 8.0, 1.6),
    ],
    "engines": [
        Engine("Двигатель Д-1", 300, 25000, 15, 2.5, 1.4),
        Engine("Двигатель Д-2", 500, 45000, 25, 3.0, 1.6),
        Engine("Двигатель Д-3", 900, 90000, 45, 3.5, 1.8),
    ],
}


# ==================== РАКЕТА ====================
class Rocket:
    def __init__(self, parts=None):
        self.parts = parts or []
        self.x = 0.0
        self.y = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.angle = 0.0
        self.throttle = 0.0
        self.alive = True
        self.max_altitude = 0.0
        self.max_speed = 0.0
        self.flight_time = 0.0

    @property
    def total_mass(self):
        return sum(p.total_mass for p in self.parts if p.alive)

    @property
    def dry_mass(self):
        return sum(p.mass for p in self.parts if p.alive)

    @property
    def fuel(self):
        return sum(p.fuel for p in self.parts if p.alive)

    @property
    def max_fuel(self):
        return sum(p.max_fuel for p in self.parts if p.alive)

    @property
    def total_thrust(self):
        return sum(p.thrust for p in self.parts if p.alive and p.active and p.fuel > 0)

    @property
    def altitude(self):
        return max(0.0, self.y)

    @property
    def speed(self):
        return math.sqrt(self.vx**2 + self.vy**2)

    @property
    def thrust_to_weight(self):
        if self.total_mass <= 0:
            return 0
        return self.total_thrust / (self.total_mass * GRAVITY)

    def total_height(self):
        return sum(p.height for p in self.parts if p.alive)

    def update(self, dt, thrusting, turning):
        if not self.alive:
            return

        self.flight_time += dt
        self.angle += turning * 40 * dt

        # Тяга
        thrust_force = 0
        if thrusting and self.fuel > 0:
            self.throttle = 1.0
            # Расход топлива с каждого бака пропорционально
            for p in self.parts:
                if p.alive and p.part_type == "tank" and p.fuel > 0:
                    used = min(p.fuel, (p.fuel / max(1, self.fuel)) * 
                              sum(e.fuel_rate for e in self.parts 
                                  if e.alive and e.part_type == "engine") * dt)
                    p.fuel = max(0, p.fuel - used)
            thrust_force = self.total_thrust
        else:
            self.throttle = 0.0

        # Ускорение от тяги
        if self.total_mass > 0:
            a_thrust = thrust_force / self.total_mass
        else:
            a_thrust = 0

        rad = math.radians(self.angle)
        ax_thrust = a_thrust * math.sin(rad)
        ay_thrust = a_thrust * math.cos(rad)

        # Гравитация
        ay_gravity = -GRAVITY

        # Сопротивление воздуха
        ax_drag = 0
        ay_drag = 0
        if self.altitude < ATMOSPHERE_HEIGHT:
            air_density = math.exp(-self.altitude / 8500)
            v = self.speed
            if v > 0:
                drag_force = DRAG_COEFF * air_density * v * v * self.total_mass
                ax_drag = -drag_force * (self.vx / v) / self.total_mass
                ay_drag = -drag_force * (self.vy / v) / self.total_mass

        ax = ax_thrust + ax_drag
        ay = ay_thrust + ay_gravity + ay_drag

        self.vx += ax * dt
        self.vy += ay * dt
        self.x += self.vx * dt
        self.y += self.vy * dt

        self.max_altitude = max(self.max_altitude, self.altitude)
        self.max_speed = max(self.max_speed, self.speed)

        # Столкновение с землёй
        if self.y < 0:
            self.y = 0
            if abs(self.vy) > 3:
                self.alive = False
            self.vx = 0
            self.vy = 0


# ==================== СОХРАНЕНИЯ ====================
class SaveManager:
    def __init__(self, filename="rocketsim_save.json"):
        self.filename = filename

    def save(self, data):
        try:
            with open(self.filename, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"Ошибка сохранения: {e}")
            return False

    def load(self):
        if not os.path.exists(self.filename):
            return None
        try:
            with open(self.filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Ошибка загрузки: {e}")
            return None


# ==================== ГЛАВНОЕ ПРИЛОЖЕНИЕ ====================
class RocketSimApp:
    def __init__(self, root):
        self.root = root
        self.root.title("RocketSim")
        self.root.configure(bg=COLORS["bg"])
        self.root.resizable(False, False)

        self.player_name = ""
        self.money = 10000
        self.unlocked_parts = ["noses", "tanks", "engines"]
        self.current_rocket_parts = []
        self.contracts_completed = 0
        self.save_manager = SaveManager()

        self.load_progress()
        self.show_main_menu()

    def load_progress(self):
        data = self.save_manager.load()
        if data:
            self.player_name = data.get("name", "")
            self.money = data.get("money", 10000)
            self.contracts_completed = data.get("contracts", 0)

    def save_progress(self):
        data = {
            "name": self.player_name,
            "money": self.money,
            "contracts": self.contracts_completed,
        }
        self.save_manager.save(data)

    def clear_screen(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    # ==================== ГЛАВНОЕ МЕНЮ ====================
    def show_main_menu(self):
        self.clear_screen()

        frame = tk.Frame(self.root, bg=COLORS["bg"])
        frame.pack(expand=True)

        title = tk.Label(frame, text="🚀 ROCKET SIM",
                         font=("Arial", 48, "bold"),
                         fg=COLORS["ui_accent"], bg=COLORS["bg"])
        title.pack(pady=30)

        if self.player_name:
            subtitle = tk.Label(frame,
                                text=f"С возвращением, {self.player_name}!",
                                font=("Arial", 16),
                                fg=COLORS["ui_text"], bg=COLORS["bg"])
            subtitle.pack(pady=10)
        else:
            subtitle = tk.Label(frame,
                                text="Симулятор ракетостроения",
                                font=("Arial", 16),
                                fg=COLORS["ui_text"], bg=COLORS["bg"])
            subtitle.pack(pady=10)

        stats = tk.Label(frame,
                         text=f"Баланс: {self.money}₽  |  Контрактов: {self.contracts_completed}",
                         font=("Arial", 12),
                         fg=COLORS["ui_ok"], bg=COLORS["bg"])
        stats.pack(pady=10)

        btn_frame = tk.Frame(frame, bg=COLORS["bg"])
        btn_frame.pack(pady=30)

        buttons = [
            ("Новая игра", self.new_game),
            ("Собрать ракету", self.show_builder),
            ("Контракты", self.show_contracts),
            ("Выход", self.root.quit),
        ]

        for text, cmd in buttons:
            b = tk.Button(btn_frame, text=text, font=("Arial", 14),
                          bg=COLORS["ui_bg"], fg=COLORS["ui_text"],
                          activebackground=COLORS["ui_accent"],
                          width=20, height=1, command=cmd,
                          relief="flat", bd=0, cursor="hand2")
            b.pack(pady=5)

    def new_game(self):
        name = simpledialog.askstring("Новая игра", "Как тебя зовут, инженер?",
                                      parent=self.root)
        if name:
            self.player_name = name.strip()
            self.money = 10000
            self.contracts_completed = 0
            self.save_progress()
            self.show_main_menu()

    # ==================== КОНСТРУКТОР ====================
    def show_builder(self):
        self.clear_screen()

        top = tk.Frame(self.root, bg=COLORS["bg"])
        top.pack(fill="x", padx=10, pady=10)

        tk.Label(top, text="🛠 Конструктор ракеты",
                 font=("Arial", 24, "bold"),
                 fg=COLORS["ui_accent"], bg=COLORS["bg"]).pack(side="left")

        tk.Button(top, text="← В меню", font=("Arial", 12),
                  bg=COLORS["ui_bg"], fg=COLORS["ui_text"],
                  command=self.show_main_menu, relief="flat").pack(side="right")

        main = tk.Frame(self.root, bg=COLORS["bg"])
        main.pack(fill="both", expand=True, padx=10, pady=10)

        # Левая панель — каталог
        left = tk.Frame(main, bg=COLORS["ui_bg"], width=300)
        left.pack(side="left", fill="y", padx=(0, 10))
        left.pack_propagate(False)

        tk.Label(left, text="Детали", font=("Arial", 16, "bold"),
                 fg=COLORS["ui_text"], bg=COLORS["ui_bg"]).pack(pady=10)

        canvas_left = tk.Canvas(left, bg=COLORS["ui_bg"], highlightthickness=0)
        canvas_left.pack(fill="both", expand=True, padx=5, pady=5)
        scroll_left = tk.Scrollbar(left, orient="vertical", command=canvas_left.yview)
        scroll_left.pack(side="right", fill="y")
        canvas_left.configure(yscrollcommand=scroll_left.set)

        inner_left = tk.Frame(canvas_left, bg=COLORS["ui_bg"])
        canvas_left.create_window((0, 0), window=inner_left, anchor="nw")

        for category, parts in PARTS_CATALOG.items():
            tk.Label(inner_left, text=category.upper(),
                     font=("Arial", 12, "bold"),
                     fg=COLORS["ui_accent"], bg=COLORS["ui_bg"]).pack(anchor="w", pady=(10, 5))
            for p in parts:
                btn = tk.Button(inner_left,
                                text=f"{p.name}\n{p.mass}кг | {p.height}м",
                                font=("Arial", 10), justify="left",
                                bg=COLORS["bg"], fg=COLORS["ui_text"],
                                command=lambda part=p: self.add_part(part),
                                relief="flat", anchor="w", padx=10, pady=5)
                btn.pack(fill="x", pady=2)

        inner_left.update_idletasks()
        canvas_left.configure(scrollregion=canvas_left.bbox("all"))

        # Центральная панель — ракета
        center = tk.Frame(main, bg=COLORS["bg"])
        center.pack(side="left", fill="both", expand=True)

        self.rocket_canvas = tk.Canvas(center, bg=COLORS["bg"], highlightthickness=0)
        self.rocket_canvas.pack(fill="both", expand=True)
        self.rocket_canvas.bind("<Button-1>", self.on_rocket_click)
        self.draw_rocket_in_builder()

        # Правая панель — инфо и кнопки
        right = tk.Frame(main, bg=COLORS["ui_bg"], width=250)
        right.pack(side="right", fill="y", padx=(10, 0))
        right.pack_propagate(False)

        tk.Label(right, text="Статистика", font=("Arial", 16, "bold"),
                 fg=COLORS["ui_text"], bg=COLORS["ui_bg"]).pack(pady=10)

        self.stats_label = tk.Label(right, text="", font=("Consolas", 11),
                                    fg=COLORS["ui_text"], bg=COLORS["ui_bg"],
                                    justify="left")
        self.stats_label.pack(pady=10, padx=10, anchor="w")

        self.update_builder_stats()

        tk.Button(right, text="Очистить", font=("Arial", 12),
                  bg=COLORS["ui_bg"], fg=COLORS["ui_warn"],
                  command=self.clear_rocket, relief="flat").pack(pady=5, fill="x", padx=10)

        tk.Button(right, text="🚀 Запустить!", font=("Arial", 14, "bold"),
                  bg=COLORS["ui_ok"], fg=COLORS["bg"],
                  command=self.launch_rocket, relief="flat").pack(pady=20, fill="x", padx=10)

    def add_part(self, part):
        new_part = part.clone()
        if new_part.part_type == "engine":
            # Двигатель — вниз
            self.current_rocket_parts.insert(0, new_part)
        elif new_part.part_type == "nose":
            # Нос — вверх
            self.current_rocket_parts.append(new_part)
        else:
            # Бак — в середину
            engines = [p for p in self.current_rocket_parts if p.part_type == "engine"]
            self.current_rocket_parts.insert(len(engines), new_part)
        self.draw_rocket_in_builder()
        self.update_builder_stats()

    def clear_rocket(self):
        self.current_rocket_parts = []
        self.draw_rocket_in_builder()
        self.update_builder_stats()

    def on_rocket_click(self, event):
        # Удаление детали кликом (последняя добавленная)
        if self.current_rocket_parts:
            self.current_rocket_parts.pop()
            self.draw_rocket_in_builder()
            self.update_builder_stats()

    def update_builder_stats(self):
        parts = self.current_rocket_parts
        if not parts:
            self.stats_label.config(text="Ракета пуста\n\nДобавь детали\nслева")
            return

        total_mass = sum(p.total_mass for p in parts)
        dry_mass = sum(p.mass for p in parts)
        fuel = sum(p.fuel for p in parts)
        thrust = sum(p.thrust for p in parts if p.part_type == "engine")
        height = sum(p.height for p in parts)
        twr = thrust / (total_mass * GRAVITY) if total_mass > 0 else 0

        text = (
            f"Деталей: {len(parts)}\n"
            f"Высота:  {height:.1f} м\n"
            f"Масса:   {total_mass:.0f} кг\n"
            f"Сухая:   {dry_mass:.0f} кг\n"
            f"Топливо: {fuel:.0f} кг\n"
            f"Тяга:    {thrust:.0f} Н\n"
            f"Т/Т:     {twr:.2f}\n"
        )
        if twr < 1:
            text += "\n⚠ Т/Т < 1\nНе взлетит!"
        elif twr > 3:
            text += "\n⚠ Т/Т > 3\nСлишком мощно!"
        self.stats_label.config(text=text)

    def draw_rocket_in_builder(self):
        c = self.rocket_canvas
        c.delete("all")

        if not self.current_rocket_parts:
            c.create_text(WIDTH//2, HEIGHT//2, text="Пусто",
                          fill=COLORS["ui_text"], font=("Arial", 20))
            return

        # Рисуем ракету вертикально, снизу вверх
        scale = 25  # пикселей на метр
        cx = WIDTH // 2
        total_h = sum(p.height for p in self.current_rocket_parts)
        y = HEIGHT - 100  # начинаем снизу

        for part in self.current_rocket_parts:
            w = part.width * scale
            h = part.height * scale
            x1 = cx - w/2
            x2 = cx + w/2
            y1 = y - h
            y2 = y

            if part.part_type == "nose":
                c.create_polygon(x1, y2, cx, y1, x2, y2,
                                 fill=part.color, outline="white")
            elif part.part_type == "engine":
                c.create_rectangle(x1, y1, x2, y2,
                                   fill=part.color, outline="white")
                c.create_polygon(cx - w*0.3, y2, cx, y2 + h*0.3, cx + w*0.3, y2,
                                 fill="#333", outline="white")
            else:
                c.create_rectangle(x1, y1, x2, y2,
                                   fill=part.color, outline="white")
                # Уровень топлива
                if part.max_fuel > 0:
                    fuel_ratio = part.fuel / part.max_fuel
                    fuel_h = h * fuel_ratio
                    c.create_rectangle(x1 + 2, y2 - fuel_h, x2 - 2, y2 - 2,
                                       fill="#4488cc", outline="")

            y = y1

    # ==================== КОНТРАКТЫ ====================
    def show_contracts(self):
        self.clear_screen()

        top = tk.Frame(self.root, bg=COLORS["bg"])
        top.pack(fill="x", padx=10, pady=10)

        tk.Label(top, text="📜 Контракты",
                 font=("Arial", 24, "bold"),
                 fg=COLORS["ui_accent"], bg=COLORS["bg"]).pack(side="left")

        tk.Button(top, text="← В меню", font=("Arial", 12),
                  bg=COLORS["ui_bg"], fg=COLORS["ui_text"],
                  command=self.show_main_menu, relief="flat").pack(side="right")

        main = tk.Frame(self.root, bg=COLORS["bg"])
        main.pack(fill="both", expand=True, padx=20, pady=20)

        contracts = [
            {"name": "Запуск спутника", "desc": "Достигни высоты 200 км",
             "check": lambda r: r.max_altitude >= 200000, "reward": 5000},
            {"name": "Суборбитальный полёт", "desc": "Пересечи линию Кармана (100 км)",
             "check": lambda r: r.max_altitude >= 100000, "reward": 3000},
            {"name": "Скоростной рекорд", "desc": "Достигни скорости 2000 м/с",
             "check": lambda r: r.max_speed >= 2000, "reward": 4000},
            {"name": "Высотный рекорд", "desc": "Достигни 500 км",
             "check": lambda r: r.max_altitude >= 500000, "reward": 8000},
            {"name": "Быстрый старт", "desc": "Достигни 50 км за 60 секунд",
             "check": lambda r: r.max_altitude >= 50000 and r.flight_time <= 60,
             "reward": 6000},
        ]

        for c in contracts:
            f = tk.Frame(main, bg=COLORS["ui_bg"])
            f.pack(fill="x", pady=5)

            tk.Label(f, text=c["name"], font=("Arial", 14, "bold"),
                     fg=COLORS["ui_text"], bg=COLORS["ui_bg"]).pack(anchor="w", padx=10, pady=5)
            tk.Label(f, text=c["desc"], font=("Arial", 11),
                     fg=COLORS["ui_text"], bg=COLORS["ui_bg"]).pack(anchor="w", padx=10)
            tk.Label(f, text=f"Награда: {c['reward']}₽", font=("Arial", 12),
                     fg=COLORS["ui_ok"], bg=COLORS["ui_bg"]).pack(anchor="e", padx=10, pady=5)

    # ==================== ЗАПУСК ====================
    def launch_rocket(self):
        if not self.current_rocket_parts:
            messagebox.showwarning("Ошибка", "Сначала собери ракету!")
            return

        # Проверка: есть ли двигатель и обтекатель
        has_engine = any(p.part_type == "engine" for p in self.current_rocket_parts)
        has_nose = any(p.part_type == "nose" for p in self.current_rocket_parts)
        if not has_engine:
            messagebox.showwarning("Ошибка", "Нужен хотя бы один двигатель!")
            return
        if not has_nose:
            messagebox.showwarning("Ошибка", "Нужен обтекатель!")
            return

        rocket = Rocket([p.clone() for p in self.current_rocket_parts])
        self.show_flight(rocket)

    def show_flight(self, rocket):
        self.clear_screen()

        self.flight_running = True
        self.rocket = rocket
        self.camera_y = 0.0
        self.stars = [(random.randint(0, WIDTH), random.randint(0, HEIGHT//2))
                      for _ in range(100)]

        # Верхняя панель
        top = tk.Frame(self.root, bg=COLORS["ui_bg"], height=40)
        top.pack(fill="x")
        top.pack_propagate(False)

        tk.Label(top, text=f"🚀 Полёт  |  {self.player_name}",
                 font=("Arial", 12), fg=COLORS["ui_text"],
                 bg=COLORS["ui_bg"]).pack(side="left", padx=10)

        self.flight_status = tk.Label(top, text="", font=("Arial", 12, "bold"),
                                      fg=COLORS["ui_ok"], bg=COLORS["ui_bg"])
        self.flight_status.pack(side="left", padx=20)

        tk.Button(top, text="← В меню", font=("Arial", 11),
                  bg=COLORS["ui_bg"], fg=COLORS["ui_text"],
                  command=self.end_flight, relief="flat").pack(side="right", padx=10)

        # Основная область
        main = tk.Frame(self.root, bg=COLORS["bg"])
        main.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(main, bg=COLORS["bg"], highlightthickness=0)
        self.canvas.pack(side="left", fill="both", expand=True)

        # Правая панель телеметрии
        right = tk.Frame(main, bg=COLORS["ui_bg"], width=280)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        tk.Label(right, text="Телеметрия", font=("Arial", 16, "bold"),
                 fg=COLORS["ui_accent"], bg=COLORS["ui_bg"]).pack(pady=10)

        self.telemetry_label = tk.Label(right, text="", font=("Consolas", 12),
                                        fg=COLORS["ui_text"], bg=COLORS["ui_bg"],
                                        justify="left")
        self.telemetry_label.pack(pady=10, padx=10, anchor="w")

        # Управление
        ctrl = tk.Frame(right, bg=COLORS["ui_bg"])
        ctrl.pack(pady=20, padx=10, fill="x")

        tk.Label(ctrl, text="Управление:", font=("Arial", 12, "bold"),
                 fg=COLORS["ui_text"], bg=COLORS["ui_bg"]).pack(anchor="w")
        tk.Label(ctrl, text="W/↑ — тяга\nA/D — поворот\nR — рестарт\nESC — выход",
                 font=("Consolas", 10), fg=COLORS["ui_text"],
                 bg=COLORS["ui_bg"], justify="left").pack(anchor="w", pady=5)

        self.throttle_var = tk.DoubleVar(value=1.0)
        tk.Label(ctrl, text="Тяга:", font=("Arial", 11),
                 fg=COLORS["ui_text"], bg=COLORS["ui_bg"]).pack(anchor="w", pady=(10, 0))
        tk.Scale(ctrl, from_=0, to=100, orient="horizontal",
                 variable=self.throttle_var, bg=COLORS["ui_bg"],
                 fg=COLORS["ui_text"], troughcolor=COLORS["bg"],
                 highlightthickness=0).pack(fill="x")

        # Привязка клавиш
        self.root.bind("<KeyPress>", self.on_key_press)
        self.root.bind("<KeyRelease>", self.on_key_release)
        self.keys_pressed = set()

        # Запуск цикла
        self.flight_loop()

    def on_key_press(self, event):
        self.keys_pressed.add(event.keysym)
        if event.keysym == "Escape":
            self.end_flight()
        if event.keysym.lower() == "r":
            self.launch_rocket()

    def on_key_release(self, event):
        self.keys_pressed.discard(event.keysym)

    def flight_loop(self):
        if not self.flight_running:
            return

        dt = 1.0 / FPS
        thrusting = ("w" in self.keys_pressed or "Up" in self.keys_pressed or
                     self.throttle_var.get() > 0)
        turning = 0
        if "a" in self.keys_pressed or "Left" in self.keys_pressed:
            turning = -1
        if "d" in self.keys_pressed or "Right" in self.keys_pressed:
            turning = 1

        self.rocket.update(dt, thrusting, turning)

        # Камера
        target = max(0, self.rocket.y - 100)
        self.camera_y += (target - self.camera_y) * 0.1

        self.draw_flight()
        self.update_telemetry()

        self.root.after(FRAME_TIME, self.flight_loop)

    def draw_flight(self):
        c = self.canvas
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()

        # Небо — градиент
        alt_ratio = min(1.0, self.rocket.altitude / ATMOSPHERE_HEIGHT)
        for i in range(h):
            t = i / h
            r = int(COLORS["sky_low"][1:3], 16) * (1-t) * (1-alt_ratio) + \
                int(COLORS["sky_high"][1:3], 16) * (t + alt_ratio)
            g = int(COLORS["sky_low"][3:5], 16) * (1-t) * (1-alt_ratio) + \
                int(COLORS["sky_high"][3:5], 16) * (t + alt_ratio)
            b = int(COLORS["sky_low"][5:7], 16) * (1-t) * (1-alt_ratio) + \
                int(COLORS["sky_high"][5:7], 16) * (t + alt_ratio)
            c.create_line(0, i, w, i, fill=f"#{int(r):02x}{int(g):02x}{int(b):02x}")

        # Звёзды в космосе
        if alt_ratio > 0.3:
            for sx, sy in self.stars:
                c.create_oval(sx, sy, sx+2, sy+2, fill=COLORS["star"])

        # Земля
        ground_y = h - 100 + self.camera_y * 0.5
        if ground_y < h:
            c.create_rectangle(0, ground_y, w, h, fill=COLORS["ground"])
            c.create_line(0, ground_y, w, ground_y, fill=COLORS["ground"], width=2)

        # Ракета
        if self.rocket.alive or self.rocket.altitude > 0:
            scale = 3
            rx = w // 2
            ry = h - 150 - (self.rocket.y - self.camera_y) * scale

            # Рисуем части ракеты
            y_pos = ry
            for part in reversed(self.rocket.parts):
                if not part.alive:
                    continue
                pw = part.width * scale * 5
                ph = part.height * scale * 5
                x1 = rx - pw/2
                x2 = rx + pw/2
                y1 = y_pos - ph
                y2 = y_pos

                if part.part_type == "nose":
                    c.create_polygon(x1, y2, rx, y1, x2, y2,
                                     fill=part.color, outline="white")
                elif part.part_type == "engine":
                    c.create_rectangle(x1, y1, x2, y2,
                                       fill=part.color, outline="white")
                    # Пламя
                    if self.rocket.throttle > 0:
                        fl = ph * self.rocket.throttle * 1.5
                        c.create_polygon(rx - pw*0.3, y2, rx, y2 + fl, rx + pw*0.3, y2,
                                         fill=COLORS["flame"], outline="")
                        c.create_polygon(rx - pw*0.15, y2, rx, y2 + fl*0.6, rx + pw*0.15, y2,
                                         fill=COLORS["flame_core"], outline="")
                else:
                    c.create_rectangle(x1, y1, x2, y2,
                                       fill=part.color, outline="white")

                y_pos = y1

        # Статус
        if not self.rocket.alive:
            self.flight_status.config(text="💥 КРУШЕНИЕ", fg=COLORS["ui_warn"])
        elif self.rocket.altitude > KARMAN_LINE:
            self.flight_status.config(text="🌌 В КОСМОСЕ", fg=COLORS["ui_ok"])
        else:
            self.flight_status.config(text="🚀 В ПОЛЁТЕ", fg=COLORS["ui_accent"])

    def update_telemetry(self):
        r = self.rocket
        text = (
            f"Высота:    {r.altitude:10.1f} м\n"
            f"Макс:      {r.max_altitude:10.1f} м\n"
            f"Скорость:  {r.speed:10.1f} м/с\n"
            f"Макс:      {r.max_speed:10.1f} м/с\n"
            f"Vx:        {r.vx:10.1f} м/с\n"
            f"Vy:        {r.vy:10.1f} м/с\n"
            f"─────────────────────\n"
            f"Масса:     {r.total_mass:10.1f} кг\n"
            f"Топливо:   {r.fuel:10.1f} кг\n"
            f"Тяга:      {r.total_thrust:10.0f} Н\n"
            f"Т/Т:       {r.thrust_to_weight:10.2f}\n"
            f"Угол:      {r.angle:10.1f} °\n"
            f"─────────────────────\n"
            f"Время:     {r.flight_time:10.1f} с\n"
        )
        self.telemetry_label.config(text=text)

    def end_flight(self):
        self.flight_running = False
        self.root.unbind("<KeyPress>")
        self.root.unbind("<KeyRelease>")
        self.show_main_menu()


# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    root = tk.Tk()
    root.geometry(f"{WIDTH}x{HEIGHT}")
    app = RocketSimApp(root)
    root.mainloop()
