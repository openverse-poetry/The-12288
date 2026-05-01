#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TERMINAL EMPIRE: INFINITE SURVIVAL
Масштабная выживалка с империями, ботами и симуляцией серверов.
Карта: 12288 x 12288 (процедурная генерация)
"""

import os
import sys
import time
import random
import math
import json
import hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum

# --- КОНФИГУРАЦИЯ ---
MAP_SIZE = 12288
CHUNK_SIZE = 64  # Размер подгружаемого куска карты
FPS = 0.5  # Задержка между ходами в секундах

# Цвета для терминала
class Colors:
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"
    BG_BLACK = "\033[40m"

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_colored(text, color=Colors.WHITE):
    print(f"{color}{text}{Colors.RESET}")

# --- СИСТЕМНЫЕ КЛАССЫ ---

class ResourceType(Enum):
    FOOD = "Еда"
    WOOD = "Дерево"
    STONE = "Камень"
    GOLD = "Золото"
    IRON = "Железо"
    POPULATION = "Люди"

@dataclass
class Item:
    name: str
    weight: float
    value: int
    item_type: str  # weapon, armor, tool, resource

@dataclass
class Unit:
    id: int
    name: str
    hp: int
    max_hp: int
    attack: int
    defense: int
    is_ai: bool
    loyalty: int  # 0-100
    role: str  # worker, soldier, slave, king
    inventory: List[Item] = field(default_factory=list)
    
    def __post_init__(self):
        self.x = 0
        self.y = 0

@dataclass
class Building:
    id: int
    name: str
    type: str  # house, farm, mine, wall, tower
    hp: int
    capacity: int
    production: Dict[ResourceType, int] = field(default_factory=dict)

@dataclass
class Chunk:
    x: int
    y: int
    data: Dict[Tuple[int, int], str] = field(default_factory=dict) # (local_x, local_y) -> terrain
    entities: List[Unit] = field(default_factory=list)
    buildings: List[Building] = field(default_factory=list)

# --- ГЕНЕРАТОР МИРА (Псевдо-случайный для огромной карты) ---
class WorldGenerator:
    def __init__(self, seed: int):
        self.seed = seed
    
    def _hash(self, x, y):
        # Детерминированный хеш для координат
        h = hashlib.sha256(f"{self.seed}-{x}-{y}".encode()).hexdigest()
        return int(h, 16)

    def get_terrain(self, x, y) -> str:
        val = self._hash(x, y) % 100
        if val < 5: return "🌊"  # Вода
        elif val < 15: return "🌲"  # Лес
        elif val < 25: return "🏔️"  # Горы
        elif val < 30: return "🏜️"  # Пустыня
        elif val < 35: return "🏰"  # Руины/Город
        else: return "🌿"  # Равнина

    def get_resources(self, x, y) -> Dict[ResourceType, int]:
        val = self._hash(x, y + 1000) % 100
        res = {}
        if val > 80: res[ResourceType.WOOD] = random.randint(1, 10)
        if val > 90: res[ResourceType.STONE] = random.randint(1, 5)
        if val > 95: res[ResourceType.GOLD] = random.randint(1, 2)
        return res

# --- ИГРОВАЯ ЛОГИКА ---

class ServerInstance:
    """Симуляция серверного экземпляра"""
    def __init__(self, name: str, owner: str, is_temporary: bool):
        self.name = name
        self.owner = owner
        self.is_temporary = is_temporary
        self.players: List[str] = []
        self.world_seed = random.randint(0, 999999)
        self.generator = WorldGenerator(self.world_seed)
        self.chunks: Dict[Tuple[int, int], Chunk] = {}
        self.nations: Dict[str, 'Nation'] = {}
        self.global_market_prices = {r: 10 for r in ResourceType}

    def get_chunk(self, gx, gy):
        cx, cy = gx // CHUNK_SIZE, gy // CHUNK_SIZE
        if (cx, cy) not in self.chunks:
            chunk = Chunk(cx, cy)
            # Генерация данных чанка
            for lx in range(CHUNK_SIZE):
                for ly in range(CHUNK_SIZE):
                    wx, wy = cx * CHUNK_SIZE + lx, cy * CHUNK_SIZE + ly
                    chunk.data[(lx, ly)] = self.generator.get_terrain(wx, wy)
            self.chunks[(cx, cy)] = chunk
        return self.chunks[(cx, cy)]

class Nation:
    def __init__(self, name: str, leader: Unit, color: str):
        self.name = name
        self.leader = leader
        self.color = color
        self.members: List[Unit] = [leader]
        self.treasury = 100
        self.territory: List[Tuple[int, int]] = []
        self.is_hostile = False

    def add_member(self, unit: Unit):
        self.members.append(unit)
        unit.loyalty = 50

class Player:
    def __init__(self, name: str, server: ServerInstance):
        self.name = name
        self.unit = Unit(
            id=0, name=name, hp=15, max_hp=15, 
            attack=2, defense=0, is_ai=False, 
            loyalty=100, role="survivor"
        )
        self.server = server
        self.inventory: List[Item] = []
        self.gold = 0
        self.nation: Optional[Nation] = None
        self.is_slave = False
        self.master: Optional[Unit] = None
        self.known_recipes = ["campfire", "spear"]
        
        # Стартовая позиция (случайная, но безопасная)
        start_x = random.randint(100, MAP_SIZE - 100)
        start_y = random.randint(100, MAP_SIZE - 100)
        self.unit.x = start_x
        self.unit.y = start_y

    def move(self, dx: int, dy: int):
        if self.is_slave:
            print_colored("Вы раб и не можете свободно перемещаться!", Colors.RED)
            return

        new_x = self.unit.x + dx
        new_y = self.unit.y + dy
        
        if 0 <= new_x < MAP_SIZE and 0 <= new_y < MAP_SIZE:
            self.unit.x = new_x
            self.unit.y = new_y
            self.check_encounters()
        else:
            print_colored("Граница мира!", Colors.YELLOW)

    def check_encounters(self):
        chunk = self.server.get_chunk(self.unit.x, self.unit.y)
        # Простая логика встреч
        if random.random() < 0.1: # 10% шанс встречи
            self.encounter_event()

    def encounter_event(self):
        events = [
            ("wild_beast", "На вас напал дикий зверь!"),
            ("traveler", "Странник предлагает торговлю."),
            ("slave_hunter", "Охотники за рабами!", True),
            ("nothing", "Ничего не произошло.")
        ]
        ev = random.choice(events)
        
        if ev[0] == "wild_beast":
            print_colored(ev[1], Colors.RED)
            dmg = random.randint(1, 3)
            self.unit.hp -= dmg
            print_colored(f"Вы получили {dmg} урона.", Colors.RED)
            if self.unit.hp <= 0:
                self.die()
        elif ev[0] == "slave_hunter":
            print_colored(ev[1], Colors.MAGENTA)
            if self.unit.hp < 5 or random.random() < 0.3:
                print_colored("Вас схватили и продали в рабство!", Colors.BOLD + Colors.RED)
                self.become_slave()
        elif ev[0] == "traveler":
            print_colored("Странник: 'Хочешь купить карту сокровищ за 50 золота?'", Colors.CYAN)

    def become_slave(self):
        self.is_slave = True
        # Найти ближайшего бота-владельца или создать нового
        owner_name = f"Lord_{random.randint(1,100)}"
        self.master = Unit(0, owner_name, 100, 100, 10, 5, True, 100, "king")
        print_colored(f"Ваш новый хозяин: {owner_name}", Colors.MAGENTA)

    def die(self):
        print_colored("☠️ ВЫ ПОГИБЛИ ☠️", Colors.RED)
        time.sleep(2)
        # Респавн или конец игры (упрощено)
        self.unit.hp = self.unit.max_hp
        self.unit.x = random.randint(0, MAP_SIZE)
        self.unit.y = random.randint(0, MAP_SIZE)
        self.inventory = []
        print_colored("Вас воскресили духи предков в случайном месте...", Colors.GREEN)

    def gather(self):
        chunk = self.server.get_chunk(self.unit.x, self.unit.y)
        lx, ly = self.unit.x % CHUNK_SIZE, self.unit.y % CHUNK_SIZE
        terrain = chunk.data.get((lx, ly), "🌿")
        
        print_colored(f"Добыча ресурсов на клетке {terrain}...", Colors.YELLOW)
        time.sleep(0.5)
        
        if terrain == "🌲":
            item = Item("Дерево", 1, 5, "resource")
            self.inventory.append(item)
            print_colored("+1 Дерево", Colors.GREEN)
        elif terrain == "🏔️":
            if random.random() > 0.5:
                item = Item("Камень", 2, 10, "resource")
                self.inventory.append(item)
                print_colored("+1 Камень", Colors.GREEN)
            else:
                print_colored("Камень слишком крепкий.", Colors.WHITE)
        elif terrain == "🌿":
            item = Item("Ягоды", 0.1, 2, "food")
            self.inventory.append(item)
            print_colored("+1 Еда", Colors.GREEN)
        else:
            print_colored("Здесь ничего нет.", Colors.WHITE)

    def build_empire(self):
        if self.gold < 100:
            print_colored("Нужно 100 золота для основания поселения.", Colors.RED)
            return
        
        self.gold -= 100
        nation_name = input("Название вашей империи: ")
        self.nation = Nation(nation_name, self.unit, Colors.BLUE)
        self.server.nations[nation_name] = self.nation
        print_colored(f"Империя {nation_name} основана!", Colors.BOLD + Colors.BLUE)

    def recruit_unit(self):
        if not self.nation:
            print_colored("Сначала создайте империю!", Colors.RED)
            return
        cost = 50
        if self.gold >= cost:
            self.gold -= cost
            new_unit = Unit(
                id=random.randint(1000,9999),
                name=f"Guard_{random.randint(1,99)}",
                hp=20, max_hp=20, attack=5, defense=2,
                is_ai=True, loyalty=80, role="soldier"
            )
            new_unit.x, new_unit.y = self.unit.x, self.unit.y
            self.nation.add_member(new_unit)
            # Простая симуляция "Облачного ИИ"
            print_colored("Загрузка нейросети для юнита... [██████████] 100%", Colors.CYAN)
            print_colored(f"Юнит {new_unit.name} нанят и обучен тактике!", Colors.GREEN)
        else:
            print_colored("Недостаточно золота (50)", Colors.RED)

    def show_status(self):
        clear_screen()
        print_colored(f"=== TERMINAL EMPIRE === [{self.server.name}]", Colors.BOLD + Colors.CYAN)
        print(f"Игрок: {self.name} | HP: {self.unit.hp}/{self.unit.max_hp} | Золото: {self.gold}")
        print(f"Координаты: [{self.unit.x}, {self.unit.y}] из [{MAP_SIZE}, {MAP_SIZE}]")
        if self.is_slave:
            print_colored(f"СТАТУС: РАБ у {self.master.name}", Colors.RED + Colors.BOLD)
        if self.nation:
            print_colored(f"Империя: {self.nation.name} | Подданных: {len(self.nation.members)}", Colors.BLUE)
        
        print("-" * 30)
        # Мини-карта (окрестности)
        print("Мини-карта (окрестности):")
        chunk = self.server.get_chunk(self.unit.x, self.unit.y)
        lx, ly = self.unit.x % CHUNK_SIZE, self.unit.y % CHUNK_SIZE
        
        map_view = ""
        for dy in range(-2, 3):
            row = ""
            for dx in range(-2, 3):
                nx, ny = lx + dx, ly + dy
                if nx == lx and ny == ly:
                    row += Colors.BOLD + "🧍" + Colors.RESET
                else:
                    if 0 <= nx < CHUNK_SIZE and 0 <= ny < CHUNK_SIZE:
                        row += chunk.data.get((nx, ny), "?")
                    else:
                        row += "."
            map_view += row + "\n"
        print(map_view)
        
        print("Инвентарь:", [i.name for i in self.inventory[-5:]]) # Показать последние 5
        print("-" * 30)

# --- ГЛАВНЫЙ ЦИКЛ ---

def main_menu():
    clear_screen()
    print_colored("╔════════════════════════════════════════╗", Colors.CYAN)
    print_colored("║   TERMINAL EMPIRE: INFINITE SURVIVAL   ║", Colors.BOLD + Colors.CYAN)
    print_colored("╚════════════════════════════════════════╝", Colors.CYAN)
    print("\n1. Одиночная игра (С ботами)")
    print("2. Создать свой сервер (Публичный/Частный)")
    print("3. Войти во временный сервер (Высокая нагрузка на хост)")
    print("4. Выход")
    
    choice = input("\nВыбор > ")
    player_name = input("Введите имя персонажа > ")
    
    server = None
    if choice == '1':
        server = ServerInstance("Official_Singleplayer", "System", False)
        # Генерация стартовых ботов-стран
        bots = ["RomeAI", "Barbarians", "MerchantsGuild"]
        for bot in bots:
            leader = Unit(0, bot, 100, 100, 5, 5, True, 100, "king")
            server.nations[bot] = Nation(bot, leader, Colors.RED)
            
    elif choice == '2':
        s_name = input("Название сервера > ")
        server = ServerInstance(s_name, player_name, False)
        print_colored(f"Сервер {s_name} запущен. Вы администратор.", Colors.GREEN)
        
    elif choice == '3':
        s_name = input("Название временной комнаты > ")
        server = ServerInstance(s_name, player_name, True)
        print_colored("Внимание: Этот сервер работает на вашем железе!", Colors.YELLOW)
        
    else:
        sys.exit()
        
    game_loop(Player(player_name, server))

def game_loop(player: Player):
    running = True
    turn = 0
    
    # Обучение (опционально)
    if not player.nation:
        print_colored("\n💡 СОВЕТ: Начните с добычи еды (🌿) и дерева (🌲). Следите за HP!", Colors.YELLOW)
        time.sleep(2)

    while running and player.unit.hp > 0:
        player.show_status()
        
        print("\nУПРАВЛЕНИЕ:")
        print("W/A/S/D - Движение | G - Добыча | I - Инвентарь/Статус")
        print("B - Построить империю | R - Нанять юнита (ИИ) | T - Торговля")
        print("Q - Меню/Выход | Z - Ждать (сон)")
        
        action = input("> ").lower()
        
        if action == 'w': player.move(0, -1)
        elif action == 's': player.move(0, 1)
        elif action == 'a': player.move(-1, 0)
        elif action == 'd': player.move(1, 0)
        elif action == 'g': player.gather()
        elif action == 'b': player.build_empire()
        elif action == 'r': player.recruit_unit()
        elif action == 'z':
            player.unit.hp = min(player.unit.hp + 2, player.unit.max_hp)
            print_colored("Вы отдохнули. HP восстановлено.", Colors.GREEN)
            turn += 1
        elif action == 'q':
            confirm = input("Сохранить и выйти? (y/n) > ")
            if confirm == 'y': running = False
        elif action == 't':
            # Простая торговля
            if player.inventory:
                item = player.inventory.pop()
                player.gold += item.value
                print_colored(f"Продано: {item.name} за {item.value} золота.", Colors.GREEN)
            else:
                print_colored("Нечего продавать.", Colors.WHITE)
        
        # Глобальные события сервера (симуляция активности других игроков)
        turn += 1
        if turn % 10 == 0:
            # Симуляция "Облачного ИИ" ботов
            if random.random() < 0.2 and not player.is_slave:
                print_colored("\n⚠️ НОВОСТЬ: Империя " + random.choice(list(player.server.nations.keys())) + " объявила войну!", Colors.RED)

    if player.unit.hp <= 0:
        print_colored("ИГРА ОКОНЧЕНА", Colors.RED)
    
    print_colored("Спасибо за игру!", Colors.CYAN)

if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print_colored("\nЭкстренное завершение...", Colors.RED)
