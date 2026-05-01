#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EMPIRE OS: OMEGA PROTOCOL
Terminal AAAA+ Survival & Empire Simulation
Map: 12,288 x 12,288 | Dynamic AI | Server/Client Architecture Simulation
"""

import os
import sys
import time
import random
import math
import json
import hashlib
import threading
import socket
import pickle
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple, Any
from enum import Enum
from collections import deque

# --- КОНФИГУРАЦИЯ ЯДРА ---
CONFIG = {
    "MAP_SIZE": 12288,
    "CHUNK_SIZE": 64,
    "FPS": 30,
    "CLOUD_AI_LATENCY": 0.1,  # Симуляция задержки облачного ИИ
    "START_HP": 15,
    "MAX_LOGS": 100,
}

# --- ЦВЕТОВАЯ ПАЛИТРА (ANSI) ---
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"
    BLINK = "\033[5m"
    
    # Foreground
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    
    # Bright
    B_RED = "\033[91m"
    B_GREEN = "\033[92m"
    B_YELLOW = "\033[93m"
    B_BLUE = "\033[94m"
    B_MAGENTA = "\033[95m"
    B_CYAN = "\033[96m"
    B_WHITE = "\033[97m"
    
    # Background
    BG_BLACK = "\033[40m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_BLUE = "\033[44m"

    @staticmethod
    def rgb(r, g, b, bg=False):
        code = 48 if bg else 38
        return f"\033[{code};2;{r};{g};{b}m"

# --- УТИЛИТЫ ---
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def typewriter(text, speed=0.01, color=Colors.WHITE):
    sys.stdout.write(color)
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(speed)
    sys.stdout.write(Colors.RESET + "\n")

def progress_bar(current, total, width=40, fill="█", empty="░", label=""):
    percent = current / total
    filled = int(width * percent)
    bar = fill * filled + empty * (width - filled)
    return f"{label} [{bar}] {percent*100:.1f}%"

# --- БИОМЫ И ГЕНЕРАЦИЯ МИРА ---
class BiomeType(Enum):
    OCEAN = "O"
    PLAINS = "."
    FOREST = "♣"
    DESERT = "~"
    MOUNTAIN = "^"
    TUNDRA = "*"
    CITY_RUINS = "▓"
    SERVER_HUB = "◆"

@dataclass
class Biome:
    type: BiomeType
    resources: Dict[str, float]
    danger_level: int
    color: str

BIOME_DATA = {
    BiomeType.OCEAN: Biome(BiomeType.OCEAN, {"fish": 0.8, "water": 1.0}, 2, Colors.BLUE),
    BiomeType.PLAINS: Biome(BiomeType.PLAINS, {"food": 0.6, "wood": 0.2}, 1, Colors.GREEN),
    BiomeType.FOREST: Biome(BiomeType.FOREST, {"wood": 0.9, "food": 0.4, "herbs": 0.3}, 3, Colors.B_GREEN),
    BiomeType.DESERT: Biome(BiomeType.DESERT, {"water": 0.1, "ore": 0.4}, 4, Colors.YELLOW),
    BiomeType.MOUNTAIN: Biome(BiomeType.MOUNTAIN, {"ore": 0.8, "stone": 0.9}, 5, Colors.B_WHITE),
    BiomeType.TUNDRA: Biome(BiomeType.TUNDRA, {"fur": 0.5, "food": 0.2}, 4, Colors.CYAN),
    BiomeType.CITY_RUINS: Biome(BiomeType.CITY_RUINS, {"tech": 0.7, "scrap": 0.8}, 6, Colors.MAGENTA),
    BiomeType.SERVER_HUB: Biome(BiomeType.SERVER_HUB, {"energy": 1.0, "data": 1.0}, 0, Colors.B_CYAN),
}

class WorldGenerator:
    def __init__(self, seed=None):
        self.seed = seed if seed else random.randint(0, 2**32)
        random.seed(self.seed)
        self.cache = {}  # Кэш чанков

    def _noise(self, x, y):
        # Упрощенный шум Перлина для скорости
        n = math.sin(x * 12.9898 + y * 78.233) * 43758.5453
        return n - math.floor(n)

    def get_biome(self, x, y) -> Biome:
        key = (x // CONFIG["CHUNK_SIZE"], y // CONFIG["CHUNK_SIZE"])
        if key not in self.cache:
            # Генерация чанка
            chunk_data = {}
            for cx in range(CONFIG["CHUNK_SIZE"]):
                for cy in range(CONFIG["CHUNK_SIZE"]):
                    gx, gy = key[0] * CONFIG["CHUNK_SIZE"] + cx, key[1] * CONFIG["CHUNK_SIZE"] + cy
                    val = self._noise(gx * 0.001, gy * 0.001)
                    val2 = self._noise(gx * 0.01, gy * 0.01)
                    
                    if val < 0.2: type_ = BiomeType.OCEAN
                    elif val < 0.4: type_ = BiomeType.PLAINS
                    elif val < 0.6: type_ = BiomeType.FOREST
                    elif val < 0.75: type_ = BiomeType.DESERT
                    elif val < 0.85: type_ = BiomeType.TUNDRA
                    elif val < 0.95: type_ = BiomeType.MOUNTAIN
                    else: type_ = BiomeType.CITY_RUINS
                    
                    # Серверные хабы редко
                    if abs(math.sin(gx)*math.cos(gy)) > 0.995:
                        type_ = BiomeType.SERVER_HUB
                        
                    chunk_data[(cx, cy)] = BIOME_DATA[type_]
            self.cache[key] = chunk_data
            
            # Очистка старого кэша (упрощенно)
            if len(self.cache) > 100:
                self.cache.pop(next(iter(self.cache)))
                
        local_x, local_y = x % CONFIG["CHUNK_SIZE"], y % CONFIG["CHUNK_SIZE"]
        return self.cache[key].get((local_x, local_y), BIOME_DATA[BiomeType.PLAINS])

# --- ИИ И СУЩНОСТИ ---
class AIState(Enum):
    IDLE = "IDLE"
    FORAGING = "FORAGING"
    BUILDING = "BUILDING"
    COMBAT = "COMBAT"
    FLEEING = "FLEEING"
    TRADING = "TRADING"
    SLAVE = "SLAVE"

@dataclass
class Entity:
    id: str
    name: str
    x: int
    y: int
    hp: int
    max_hp: int
    inventory: Dict[str, int]
    faction: str
    ai_state: AIState = AIState.IDLE
    is_bot: bool = True
    memory: List[str] = field(default_factory=list)
    
    def take_damage(self, amount):
        self.hp -= amount
        return self.hp <= 0

class CloudAI:
    """Симуляция обученного облачного ИИ"""
    def __init__(self):
        self.models_loaded = False
        
    def decide_action(self, entity: Entity, world: 'World') -> str:
        time.sleep(CONFIG["CLOUD_AI_LATENCY"]) # Симуляция запроса к облаку
        
        # Простая логика принятия решений на основе состояния
        if entity.hp < entity.max_hp * 0.3:
            return "FLEE"
        
        if entity.ai_state == AIState.SLAVE:
            return "WORK"
            
        if not entity.inventory.get("food", 0) > 5:
            return "GATHER_FOOD"
            
        if random.random() < 0.05:
            return "EXPLORE"
            
        # Взаимодействие с игроком
        dist = math.hypot(entity.x - world.player.x, entity.y - world.player.y)
        if dist < 5 and world.player.faction != entity.faction:
            if entity.hp > world.player.hp:
                return "ATTACK"
            else:
                return "TRADE"
                
        return "IDLE"

# --- ИГРОК И ИНТЕРФЕЙС ---
class Player(Entity):
    def __init__(self, name):
        super().__init__(
            id="player_001",
            name=name,
            x=CONFIG["MAP_SIZE"]//2,
            y=CONFIG["MAP_SIZE"]//2,
            hp=CONFIG["START_HP"],
            max_hp=CONFIG["START_HP"],
            inventory={"food": 2, "water": 2},
            faction="Nomad",
            is_bot=False
        )
        self.level = 1
        self.exp = 0
        self.gold = 0
        self.server_hosted = None

class GameUI:
    def __init__(self):
        self.width = 80
        self.height = 24
        
    def draw_header(self, player: Player, day: int):
        hp_bar = progress_bar(player.hp, player.max_hp, 20, "♥", "♡", "HP")
        hunger_bar = progress_bar(player.inventory.get("food", 0), 10, 20, "≡", "-", "FOOD")
        
        header = f"""
{Colors.BG_BLUE}{Colors.B_WHITE} EMPIRE OS: OMEGA PROTOCOL {Colors.RESET} {Colors.DIM}v1.0.4a{Colors.RESET}
Day: {day} | Pos: [{player.x}, {player.y}] | Gold: {player.gold} | Lvl: {player.level}
{Colors.RED}{hp_bar}{Colors.RESET}  {Colors.YELLOW}{hunger_bar}{Colors.RESET}
{Colors.DIM}------------------------------------------------------------{Colors.RESET}
"""
        print(header)

    def draw_minimap(self, player: Player, world: 'World', size=15):
        print(f"{Colors.DIM}--- LOCAL SCAN (RADAR) ---{Colors.RESET}")
        half = size // 2
        grid = []
        for dy in range(-half, half + 1):
            row = ""
            for dx in range(-half, half + 1):
                nx, ny = player.x + dx, player.y + dy
                if nx == player.x and ny == player.y:
                    row += f"{Colors.B_GREEN}@{Colors.RESET}"
                else:
                    biome = world.get_biome(nx, ny)
                    # Проверка на сущности
                    entity_here = next((e for e in world.entities if e.x == nx and e.y == ny and e != player), None)
                    if entity_here:
                        symbol = "☠" if entity_here.ai_state == AIState.COMBAT else "☺"
                        color = Colors.RED if entity_here.faction != player.faction else Colors.GREEN
                        row += f"{color}{symbol}{Colors.RESET}"
                    else:
                        row += f"{biome.color}{biome.type.value}{Colors.RESET}"
            grid.append(row)
        
        for line in grid:
            print(line)

    def draw_log(self, logs: deque):
        print(f"\n{Colors.DIM}--- SYSTEM LOG ---{Colors.RESET}")
        for log in list(logs)[-5:]:
            prefix = f"{Colors.B_YELLOW}[!]{Colors.RESET}" if "WARNING" in log else f"{Colors.DIM}[i]{Colors.RESET}"
            print(f"{prefix} {log}")

    def draw_menu(self):
        menu = f"""
{Colors.B_WHITE} ACTIONS {Colors.RESET}
[W] Move Up    [S] Move Down  [A] Left  [D] Right
[G] Gather     [B] Build      [I] Inv   [M] Map
[T] Trade      [F] Flee       [H] Host Server
[Q] Quit
"""
        print(menu)

# --- ОСНОВНОЙ КЛАСС ИГРЫ ---
class World:
    def __init__(self, player_name):
        self.generator = WorldGenerator()
        self.player = Player(player_name)
        self.entities: List[Entity] = []
        self.logs = deque(maxlen=CONFIG["MAX_LOGS"])
        self.day = 1
        self.cloud_ai = CloudAI()
        self.running = True
        self.servers = {} # Симуляция серверов
        
        self.log("System initialized. Welcome to the Infinite Map.")
        self.log(f"Map size: {CONFIG['MAP_SIZE']}x{CONFIG['MAP_SIZE']} cells.")
        self.spawn_initial_world()

    def log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        self.logs.append(f"[{timestamp}] {message}")

    def spawn_initial_world(self):
        # Создание бот-фракций
        factions = ["Red Empire", "Blue Syndicate", "Green Clans", "Yellow Traders"]
        for i in range(20):
            f = random.choice(factions)
            x = random.randint(0, CONFIG["MAP_SIZE"])
            y = random.randint(0, CONFIG["MAP_SIZE"])
            bot = Entity(
                id=f"bot_{i}",
                name=f"{f} Unit {i}",
                x=x, y=y,
                hp=random.randint(20, 50),
                max_hp=50,
                inventory={"food": 5},
                faction=f
            )
            self.entities.append(bot)
        self.log("World populated with initial factions.")

    def get_biome(self, x, y):
        return self.generator.get_biome(x, y)

    def update_entities(self):
        for ent in self.entities:
            if ent.is_bot:
                action = self.cloud_ai.decide_action(ent, self)
                self.process_bot_action(ent, action)

    def process_bot_action(self, bot, action):
        if action == "FLEE":
            bot.x += random.randint(-2, 2)
            bot.y += random.randint(-2, 2)
            bot.ai_state = AIState.FLEEING
        elif action == "GATHER_FOOD":
            biome = self.get_biome(bot.x, bot.y)
            if biome.resources.get("food", 0) > 0:
                bot.inventory["food"] = bot.inventory.get("food", 0) + 1
                bot.ai_state = AIState.FORAGING
        elif action == "ATTACK":
            # Логика атаки игрока
            dist = math.hypot(bot.x - self.player.x, bot.y - self.player.y)
            if dist < 1.5:
                dmg = random.randint(1, 5)
                self.player.take_damage(dmg)
                self.log(f"{Colors.RED}WARNING: {bot.name} attacked you for {dmg} DMG!{Colors.RESET}")
                bot.ai_state = AIState.COMBAT
            else:
                # Движение к игроку
                dx = 1 if self.player.x > bot.x else -1
                dy = 1 if self.player.y > bot.y else -1
                bot.x += dx
                bot.y += dy

    def host_server(self, server_type="PUBLIC"):
        port = random.randint(10000, 60000)
        server_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
        self.servers[server_id] = {
            "type": server_type,
            "port": port,
            "players": 1,
            "uptime": 0
        }
        self.log(f"{Colors.B_GREEN}SERVER HOSTED:{Colors.RESET} ID={server_id}, Type={server_type}, Port={port}")
        self.log("Resources allocated from your local machine simulation.")
        return server_id

    def game_loop(self):
        ui = GameUI()
        last_time = time.time()
        
        while self.running:
            current_time = time.time()
            if current_time - last_time >= 1.0 / CONFIG["FPS"]:
                last_time = current_time
                
                clear_screen()
                ui.draw_header(self.player, self.day)
                ui.draw_minimap(self.player, self)
                ui.draw_log(self.logs)
                ui.draw_menu()
                
                # Обработка ввода (неблокирующая эмуляция)
                # В реальном приложении здесь был бы curses или asyncio
                try:
                    # Эмуляция ввода через input с таймаутом сложна в стандартном Python без библиотек
                    # Поэтому используем простой input блокирующий, но быстрый
                    # Для "AAAA+" эффекта сделаем меню выбора действия
                    pass 
                except:
                    pass
                
                # Для демонстрации в этом формате, мы будем запрашивать действие
                # В полной версии это было бы асинхронное событие
                action = input(f"\n{Colors.B_CYAN}CMD>{Colors.RESET} ").strip().lower()
                
                if action == 'q': break
                elif action == 'w': self.player.y -= 1
                elif action == 's': self.player.y += 1
                elif action == 'a': self.player.x -= 1
                elif action == 'd': self.player.x += 1
                elif action == 'g':
                    biome = self.get_biome(self.player.x, self.player.y)
                    res = random.choice(list(biome.resources.keys()))
                    amt = int(biome.resources[res] * 10)
                    self.player.inventory[res] = self.player.inventory.get(res, 0) + amt
                    self.log(f"Gathered {amt} {res}.")
                elif action == 'h':
                    st = input("Type (PUBLIC/PRIVATE/TEMP): ").upper() or "PUBLIC"
                    self.host_server(st)
                elif action == 'i':
                    print(f"Inventory: {self.player.inventory}")
                    input("Press Enter...")
                elif action == 'm':
                    print("Map functionality expanded in full version.")
                    time.sleep(1)
                
                # Обновление мира
                self.update_entities()
                
                # Проверка смерти
                if self.player.hp <= 0:
                    clear_screen()
                    print(f"{Colors.B_RED}CRITICAL FAILURE. YOU DIED.{Colors.RESET}")
                    print("Your empire has fallen. Data archived.")
                    break
                
                # Смена дня
                if random.random() < 0.01:
                    self.day += 1
                    self.log(f"Day {self.day} started.")

if __name__ == "__main__":
    try:
        clear_screen()
        print(f"{Colors.B_CYAN}Initializing EMP IRE OS KERNEL...{Colors.RESET}")
        time.sleep(1)
        print(f"{Colors.B_GREEN}Loading 12,288x12,288 Terrain Generator...{Colors.RESET}")
        time.sleep(0.5)
        print(f"{Colors.B_YELLOW}Connecting to Cloud AI Cluster...{Colors.RESET}")
        time.sleep(0.5)
        
        name = input(f"\nEnter Operative Name: {Colors.B_WHITE}")
        print(f"{Colors.RESET}")
        
        game = World(name)
        game.game_loop()
        
    except KeyboardInterrupt:
        print("\nSession terminated by user.")
    except Exception as e:
        print(f"{Colors.B_RED}SYSTEM ERROR: {e}{Colors.RESET}")
        # В реальной игре тут была бы отправка отчета об ошибке на сервер
