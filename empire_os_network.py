#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EMPIRE OS: OMEGA PROTOCOL - NETWORK EDITION
AAAA+ Terminal Survival Game
Map: 12,288 x 12,288 | Cloud AI | Multiplayer Simulation
"""

import os
import sys
import time
import random
import math
import hashlib
import json
import threading
import socket
import select
from datetime import datetime
from collections import deque
from enum import Enum

# --- КОНФИГУРАЦИЯ ---
MAP_SIZE = 12288
CHUNK_SIZE = 16
VIEW_RANGE = 4
FPS = 30

# Цвета ANSI
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BG_BLACK = "\033[40m"
    BG_BLUE = "\033[44m"
    BG_GREEN = "\033[42m"
    BG_RED = "\033[41m"

# --- ГЕНЕРАТОР ШУМА (Упрощенный Перлин) ---
class NoiseGenerator:
    def __init__(self, seed):
        self.seed = seed
        self.perm = list(range(512))
        random.seed(seed)
        random.shuffle(self.perm)

    def _fade(self, t):
        return t * t * t * (t * (t * 6 - 15) + 10)

    def _lerp(self, a, b, t):
        return a + t * (b - a)

    def _grad(self, hash_val, x, y):
        h = hash_val & 15
        u = x if h < 8 else y
        v = y if h < 4 else x
        return u if (h & 1) == 0 else -u if (h & 2) == 0 else v if (h & 1) == 0 else -v

    def noise(self, x, y):
        X = int(x) & 255
        Y = int(y) & 255
        x -= int(x)
        y -= int(y)
        u = self._fade(x)
        v = self._fade(y)
        A = self.perm[X] + Y
        B = self.perm[X + 1] + Y
        return self._lerp(
            self._lerp(self._grad(self.perm[A], x, y), self._grad(self.perm[B], x - 1, y), u),
            self._lerp(self._grad(self.perm[A + 1], x, y - 1), self._grad(self.perm[B + 1], x - 1, y - 1), u),
            v
        )

# --- ТИПЫ БИОМОВ И РЕСУРСОВ ---
class Biome(Enum):
    OCEAN = "🌊"
    FOREST = "🌲"
    PLAINS = "🌾"
    DESERT = "🏜️"
    MOUNTAIN = "🏔️"
    TUNDRA = "❄️"
    RUINS = "🏚️"
    SERVER_HUB = "📡"

class Resource(Enum):
    NONE = "."
    FOOD = "🍎"
    WATER = "💧"
    WOOD = "🪵"
    ORE = "🪨"
    ENERGY = "⚡"
    DATA = "💾"

# --- ИГРОВЫЕ СУЩНОСТИ ---
class Entity:
    def __init__(self, x, y, name, hp=100, is_bot=True):
        self.x = x
        self.y = y
        self.name = name
        self.hp = hp
        self.max_hp = hp
        self.is_bot = is_bot
        self.inventory = {}
        self.faction = "Neutral"
        self.state = "IDLE" # IDLE, MOVING, FIGHTING, TRADING
        self.ai_level = 1.0

    def distance_to(self, other):
        return math.sqrt((self.x - other.x)**2 + (self.y - other.y)**2)

class Player(Entity):
    def __init__(self, x, y, name):
        super().__init__(x, y, name, hp=15, is_bot=False)
        self.hunger = 100
        self.thirst = 100
        self.level = 1
        self.exp = 0
        self.gold = 0
        self.server_id = None
        self.is_host = False
        self.slaves = []
        self.friends = []
        self.buildings = []

# --- СЕТЕВОЙ МЕНЕДЖЕР (СИМУЛЯЦИЯ) ---
class NetworkManager:
    def __init__(self):
        self.active_servers = {} # id -> server_data
        self.my_server = None
    
    def generate_server_id(self):
        return "".join(random.choices("0123456789ABCDEF", k=6))

    def create_server(self, name, mode="public", password=None):
        sid = self.generate_server_id()
        while sid in self.active_servers:
            sid = self.generate_server_id()
        
        self.active_servers[sid] = {
            "name": name,
            "host": "localhost", # В реальной игре тут был бы IP
            "port": random.randint(10000, 60000),
            "mode": mode, # public, private, temp
            "password": password,
            "players": [],
            "created_at": time.time(),
            "seed": random.randint(0, 999999)
        }
        self.my_server = sid
        return sid

    def connect_to_server(self, server_id):
        if server_id not in self.active_servers:
            return False, "Сервер не найден или отключен."
        
        server = self.active_servers[server_id]
        if server["mode"] == "private":
            # В реальной игре тут запрос пароля
            pass 
        
        return True, f"Подключение к серверу {server['name']}..."

    def list_servers(self):
        return self.active_servers

# --- ИИ БОТОВ ---
class CloudAI:
    def __init__(self):
        self.learning_rate = 0.01
        self.memory = {}

    def decide_action(self, bot, player, world_map):
        # Простая эвристика с элементами "обучения"
        dist = bot.distance_to(player)
        
        if bot.hp < 20:
            return "FLEE"
        if dist < 2 and bot.faction != player.faction:
            if bot.ai_level > random.random():
                return "ATTACK"
            return "TRADE"
        if dist > 10:
            return "EXPLORE"
        return "IDLE"

# --- ОСНОВНОЙ КЛАСС ИГРЫ ---
class EmpireGame:
    def __init__(self):
        self.player = None
        self.world_map = {} # Координаты -> объект клетки
        self.entities = []
        self.noise_gen = None
        self.net_manager = NetworkManager()
        self.cloud_ai = CloudAI()
        self.running = True
        self.logs = deque(maxlen=10)
        self.current_server_id = None
        self.is_multiplayer = False

    def log(self, msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"[{timestamp}] {msg}")

    def init_world(self, seed=None):
        if seed is None:
            seed = random.randint(0, 999999)
        self.noise_gen = NoiseGenerator(seed)
        self.log(f"Генерация мира 12288x12288 (Seed: {seed})...")
        
        # Генерируем только стартовую зону для оптимизации памяти при старте
        # Полный мир генерируется по чанкам при движении (в полной версии)
        # Здесь эмулируем наличие огромного мира
        start_x, start_y = MAP_SIZE // 2, MAP_SIZE // 2
        
        # Создаем ботов
        factions = ["Red Empire", "Blue Syndicate", "Green Tribe", "Yellow Corp"]
        for i in range(20):
            bx = random.randint(0, MAP_SIZE-1)
            by = random.randint(0, MAP_SIZE-1)
            bot = Entity(bx, by, f"Bot_{i}", hp=random.randint(20, 100))
            bot.faction = random.choice(factions)
            bot.ai_level = random.uniform(0.5, 1.0)
            self.entities.append(bot)
        
        self.log("Мир сгенерирован. Боты активированы.")

    def get_biome(self, x, y):
        # Нормализация координат
        nx, ny = x / 500, y / 500
        n = self.noise_gen.noise(nx, ny)
        
        if n < -0.5: return Biome.OCEAN
        elif n < 0.0: return Biome.PLAINS
        elif n < 0.3: return Biome.FOREST
        elif n < 0.6: return Biome.DESERT
        elif n < 0.8: return Biome.MOUNTAIN
        else: return Biome.TUNDRA

    def get_resource(self, x, y, biome):
        roll = random.random()
        if biome == Biome.FOREST and roll < 0.3: return Resource.WOOD
        if biome == Biome.PLAINS and roll < 0.2: return Resource.FOOD
        if biome == Biome.MOUNTAIN and roll < 0.4: return Resource.ORE
        if biome == Biome.SERVER_HUB: return Resource.DATA
        return Resource.NONE

    def render_mini_map(self):
        size = 9
        offset = size // 2
        px, py = self.player.x, self.player.y
        
        map_str = ""
        for dy in range(-offset, offset + 1):
            line = ""
            for dx in range(-offset, offset + 1):
                x, y = px + dx, py + dy
                
                if x == px and y == py:
                    line += f"{Colors.GREEN}🧍{Colors.RESET}"
                    continue
                
                # Проверка на сущности
                entity_here = next((e for e in self.entities if e.x == x and e.y == y), None)
                if entity_here:
                    color = Colors.RED if entity_here.faction != self.player.faction else Colors.CYAN
                    line += f"{color}👤{Colors.RESET}"
                    continue

                # Генерация клетки на лету
                if 0 <= x < MAP_SIZE and 0 <= y < MAP_SIZE:
                    biome = self.get_biome(x, y)
                    res = self.get_resource(x, y, biome)
                    symbol = biome.value
                    if res != Resource.NONE:
                        symbol = res.value
                    line += symbol
                else:
                    line += "⬛" # Граница мира
            map_str += line + "\n"
        return map_str

    def draw_ui(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"{Colors.BOLD}{Colors.CYAN}╔══════════════════════════════════════════════════════════╗{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}║  EMPIRE OS: OMEGA PROTOCOL [NETWORK EDITION]           ║{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}╠══════════════════════════════════════════════════════════╣{Colors.RESET}")
        
        # Статы
        p = self.player
        status_color = Colors.GREEN if p.hp > 5 else Colors.RED
        print(f"║ HP: {status_color}{p.hp}/{p.max_hp}{Colors.RESET} | ❤️  Голод: {p.hunger}% | 💧 Жажда: {p.thirst}%")
        print(f"║ 📍 Коорд: [{p.x}, {p.y}] | 🎒 Золото: {p.gold} | 🆔 Сервер: {self.current_server_id or 'OFFLINE'}")
        print(f"{Colors.BOLD}{Colors.CYAN}╠══════════════════════════════════════════════════════════╣{Colors.RESET}")
        
        # Мини-карта
        print(self.render_mini_map())
        
        # Лог событий
        print(f"{Colors.BOLD}{Colors.YELLOW}--- СОБЫТИЯ ---{Colors.RESET}")
        for log in list(self.logs)[-5:]:
            print(f"  {log}")
        
        # Управление
        print(f"\n{Colors.WHITE}WASD - Движение | G - Сбор | I - Инвентарь | H - Хостинг | C - Подкл. | Q - Выход{Colors.RESET}")

    def move_player(self, dx, dy):
        new_x = self.player.x + dx
        new_y = self.player.y + dy
        
        if 0 <= new_x < MAP_SIZE and 0 <= new_y < MAP_SIZE:
            self.player.x = new_x
            self.player.y = new_y
            # Потребление ресурсов
            self.player.hunger = max(0, self.player.hunger - 1)
            self.player.thirst = max(0, self.player.thirst - 1)
            
            if self.player.hunger == 0 or self.player.thirst == 0:
                dmg = 5
                self.player.hp -= dmg
                self.log(f"Вы теряете {dmg} HP от истощения!")
            
            # Взаимодействие с ботами
            for bot in self.entities:
                if bot.x == new_x and bot.y == new_y:
                    action = self.cloud_ai.decide_action(bot, self.player, None)
                    if action == "ATTACK":
                        dmg = random.randint(5, 15)
                        self.player.hp -= dmg
                        self.log(f"{Colors.RED}⚔️ {bot.name} атакует вас на {dmg} урона!{Colors.RESET}")
                    elif action == "TRADE":
                        self.log(f"{Colors.CYAN}🤝 {bot.name} хочет торговать.{Colors.RESET}")
        else:
            self.log("Граница мира достигнута.")

    def gather(self):
        biome = self.get_biome(self.player.x, self.player.y)
        res = self.get_resource(self.player.x, self.player.y, biome)
        
        if res != Resource.NONE:
            amount = random.randint(1, 5)
            self.log(f"Добыто: {res.name} x{amount}")
            # Упрощенная система инвентаря
            self.player.gold += amount * 10
        else:
            self.log("Здесь ничего нет.")

    def network_menu(self):
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            print(f"{Colors.BOLD}{Colors.BLUE}=== СЕТЕВОЕ МЕНЮ ==={Colors.RESET}")
            print("1. Создать свой сервер")
            print("2. Подключиться по ID")
            print("3. Список активных серверов")
            print("4. Назад")
            
            choice = input("\nВыбор > ")
            
            if choice == '1':
                name = input("Название сервера: ")
                mode = input("Режим (public/private/temp) [public]: ") or "public"
                pwd = None
                if mode == "private":
                    pwd = input("Пароль: ")
                
                sid = self.net_manager.create_server(name, mode, pwd)
                self.current_server_id = sid
                self.is_multiplayer = True
                self.player.is_host = True
                self.log(f"{Colors.GREEN}Сервер создан! Ваш ID: {sid}{Colors.RESET}")
                print(f"Отправьте этот код друзьям: {Colors.BOLD}{sid}{Colors.RESET}")
                input("Нажмите Enter...")
                break
                
            elif choice == '2':
                target_id = input("Введите ID сервера (6 символов): ").strip().upper()
                if len(target_id) != 6:
                    print("Неверный формат ID.")
                    time.sleep(1)
                    continue
                
                success, msg = self.net_manager.connect_to_server(target_id)
                if success:
                    self.current_server_id = target_id
                    self.is_multiplayer = True
                    self.log(f"{Colors.GREEN}Подключено к серверу {target_id}{Colors.RESET}")
                    # В реальной игре здесь была бы загрузка состояния мира от хоста
                    self.init_world(seed=42) # Заглушка синхронизации
                    break
                else:
                    print(msg)
                    time.sleep(1)
                    
            elif choice == '3':
                servers = self.net_manager.list_servers()
                if not servers:
                    print("Нет активных серверов.")
                else:
                    for sid, data in servers.items():
                        print(f"ID: {sid} | Name: {data['name']} | Mode: {data['mode']} | Players: {len(data['players'])}")
                input("Нажмите Enter...")
                
            elif choice == '4':
                break

    def run(self):
        print(f"{Colors.BOLD}Загрузка EMPIRE OS...{Colors.RESET}")
        time.sleep(1)
        
        name = input("Введите имя персонажа: ") or "Survivor"
        self.player = Player(MAP_SIZE//2, MAP_SIZE//2, name)
        
        # Главное меню
        while True:
            os.system('cls' if os.name == 'nt' else 'clear')
            print(f"{Colors.BOLD}{Colors.CYAN}EMPIRE OS: ГЛАВНОЕ МЕНЮ{Colors.RESET}")
            print("1. Новая игра (Одиночная)")
            print("2. Сеть (Подключиться/Создать)")
            print("3. Выход")
            
            cmd = input("> ")
            if cmd == '1':
                self.init_world()
                self.current_server_id = "SINGLEPLAYER"
                break
            elif cmd == '2':
                self.network_menu()
                if self.current_server_id:
                    self.init_world() # Загрузка мира сервера
                    break
            elif cmd == '3':
                sys.exit(0)

        # Игровой цикл
        while self.running:
            self.draw_ui()
            
            if self.player.hp <= 0:
                print(f"\n{Colors.RED}☠️ ВЫ ПОГИБЛИ. Игра окончена.{Colors.RESET}")
                input("Нажмите Enter для выхода...")
                break
            
            action = input("\nДействие > ").strip().lower()
            
            if action == 'w': self.move_player(0, -1)
            elif action == 's': self.move_player(0, 1)
            elif action == 'a': self.move_player(-1, 0)
            elif action == 'd': self.move_player(1, 0)
            elif action == 'g': self.gather()
            elif action == 'h': self.network_menu() # Быстрый доступ к хостингу
            elif action == 'c': self.network_menu() # Быстрый доступ к подключению
            elif action == 'i':
                self.log(f"Инвентарь: Золото {self.player.gold}, Предметов: 0")
            elif action == 'q':
                confirm = input("Сохранить и выйти? (y/n): ")
                if confirm.lower() == 'y':
                    self.running = False
            else:
                if action: self.log("Неизвестная команда.")

if __name__ == "__main__":
    try:
        game = EmpireGame()
        game.run()
    except KeyboardInterrupt:
        print("\nЭкстренное завершение...")
        sys.exit(0)
