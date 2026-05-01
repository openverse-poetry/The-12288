#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EMPIRE OS: OMEGA PROTOCOL - AAAA+ TERMINAL SURVIVAL
---------------------------------------------------
Масштабная симуляция выживания, империй и ИИ на карте 12288x12288.
Требования: Python 3.8+
Зависимости: нет (использует стандартную библиотеку)
"""

import os
import sys
import math
import random
import time
import threading
import json
import hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set, Any
from enum import Enum, auto
from collections import deque
import copy

# ==============================================================================
# КОНФИГУРАЦИЯ И КОНСТАНТЫ
# ==============================================================================

CONFIG = {
    "WORLD_SIZE": 12288,
    "CHUNK_SIZE": 64,
    "VIEW_RADIUS": 6,
    "MAX_ENTITIES_PER_CHUNK": 50,
    "AI_TICK_RATE": 0.5,  # Секунды между действиями ИИ
    "SERVER_TICK_RATE": 1.0,
    "STARTING_HP": 15,
    "STARTING_FOOD": 100,
    "STARTING_WATER": 100,
    "COLORS": {
        "reset": "\033[0m",
        "bold": "\033[1m",
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "magenta": "\033[95m",
        "cyan": "\033[96m",
        "white": "\033[97m",
        "gray": "\033[90m",
        "bg_blue": "\033[44m",
        "bg_green": "\033[42m",
        "bg_red": "\033[41m",
    }
}

class Biome(Enum):
    OCEAN = "🌊"
    BEACH = "🏖️"
    PLAINS = "🌾"
    FOREST = "🌲"
    MOUNTAIN = "🏔️"
    DESERT = "🏜️"
    TUNDRA = "❄️"
    RUINS = "🏚️"
    SERVER_HUB = "🖥️"

class ResourceType(Enum):
    FOOD = "Еда"
    WATER = "Вода"
    WOOD = "Дерево"
    ORE = "Руда"
    ENERGY = "Энергия"
    DATA = "Данные"
    SCRAPS = "Лом"

class EntityType(Enum):
    PLAYER = "Игрок"
    BOT = "Бот"
    CITY = "Город"
    RESOURCE_NODE = "Ресурс"
    STRUCTURE = "Постройка"

class EntityState(Enum):
    IDLE = "Бездействие"
    MOVING = "Движение"
    GATHERING = "Сбор"
    FIGHTING = "Бой"
    BUILDING = "Строительство"
    TRADING = "Торговля"
    SLAVE = "Раб"
    PRISONER = "Пленник"
    DEAD = "Мертв"

# ==============================================================================
# УТИЛИТЫ И ГЕНЕРАТОРЫ
# ==============================================================================

class SimpleNoise:
    """Упрощенная реализация шума для генерации ландшафта без внешних зависимостей."""
    def __init__(self, seed: int):
        self.seed = seed
        self.permutation = list(range(256))
        random.seed(seed)
        random.shuffle(self.permutation)
        self.permutation += self.permutation

    def _fade(self, t: float) -> float:
        return t * t * t * (t * (t * 6 - 15) + 10)

    def _lerp(self, a: float, b: float, t: float) -> float:
        return a + t * (b - a)

    def _grad(self, hash_val: int, x: float, y: float) -> float:
        h = hash_val & 3
        u = x if h < 2 else y
        v = y if h < 2 else x
        return u if (h & 1) == 0 else -u if (h & 2) == 0 else v if (h & 1) == 0 else -v

    def noise(self, x: float, y: float) -> float:
        X = int(math.floor(x)) & 255
        Y = int(math.floor(y)) & 255
        x -= math.floor(x)
        y -= math.floor(y)
        u = self._fade(x)
        v = self._fade(y)
        p = self.permutation
        A = p[X] + Y
        B = p[X + 1] + Y
        return self._lerp(
            self._lerp(self._grad(p[A], x, y), self._grad(p[B], x - 1, y), u),
            self._lerp(self._grad(p[A + 1], x, y - 1), self._grad(p[B + 1], x - 1, y - 1), u),
            v
        )

def generate_world_seed() -> int:
    return random.randint(0, 2**32 - 1)

# ==============================================================================
# КЛАССЫ СУЩНОСТЕЙ
# ==============================================================================

@dataclass
class Position:
    x: int
    y: int

    def distance_to(self, other: 'Position') -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

    def __add__(self, other: 'Position') -> 'Position':
        return Position(self.x + other.x, self.y + other.y)

    def __hash__(self):
        return hash((self.x, self.y))

@dataclass
class Inventory:
    items: Dict[ResourceType, int] = field(default_factory=dict)
    capacity: int = 50

    def add(self, res: ResourceType, amount: int):
        self.items[res] = self.items.get(res, 0) + amount

    def remove(self, res: ResourceType, amount: int) -> bool:
        if self.items.get(res, 0) >= amount:
            self.items[res] -= amount
            return True
        return False

    def get(self, res: ResourceType) -> int:
        return self.items.get(res, 0)

@dataclass
class Stats:
    hp: int = CONFIG["STARTING_HP"]
    max_hp: int = CONFIG["STARTING_HP"]
    food: float = CONFIG["STARTING_FOOD"]
    water: float = CONFIG["STARTING_WATER"]
    strength: int = 1
    intelligence: int = 1
    charisma: int = 1
    level: int = 1
    exp: int = 0

    def is_alive(self) -> bool:
        return self.hp > 0

class AIBrain:
    """Облачный ИИ (симуляция) с обучением через опыт."""
    def __init__(self, personality: str = "neutral"):
        self.personality = personality
        self.memory = []  # История действий
        self.knowledge = {}  # Изученные рецепты, карты
        self.learning_rate = 0.1
        self.state = EntityState.IDLE
        self.target: Optional[Position] = None
        self.goal: str = "survive"

    def think(self, entity: 'Entity', world_view: dict) -> str:
        # Простая логика принятия решений на основе состояния
        if entity.stats.hp < entity.stats.max_hp * 0.3:
            self.goal = "heal"
        elif entity.stats.food < 20 or entity.stats.water < 20:
            self.goal = "gather_food"
        elif self.personality == "aggressive" and random.random() < 0.1:
            self.goal = "attack"
        
        # Симуляция обучения: запоминание успешных действий
        if random.random() < 0.05:
            self.learning_rate += 0.01
        
        return self.goal

class Entity:
    def __init__(self, eid: str, etype: EntityType, pos: Position, name: str):
        self.id = eid
        self.type = etype
        self.pos = pos
        self.name = name
        self.stats = Stats()
        self.inventory = Inventory()
        self.ai = AIBrain() if etype == EntityType.BOT else None
        self.state = EntityState.IDLE
        self.faction: Optional[str] = None
        self.owner: Optional[str] = None  # Для рабов/юнитов
        self.is_slave = False
        self.skills = {}

    def move(self, dx: int, dy: int, world: 'World'):
        new_x = self.pos.x + dx
        new_y = self.pos.y + dy
        
        # Проверка границ
        if not (0 <= new_x < CONFIG["WORLD_SIZE"] and 0 <= new_y < CONFIG["WORLD_SIZE"]):
            return False
        
        # Проверка проходимости (упрощенно)
        biome = world.get_biome(new_x, new_y)
        if biome == Biome.OCEAN:
            return False
            
        self.pos = Position(new_x, new_y)
        return True

    def take_damage(self, amount: int):
        self.stats.hp -= amount
        if self.stats.hp <= 0:
            self.state = EntityState.DEAD

    def heal(self, amount: int):
        self.stats.hp = min(self.stats.hp + amount, self.stats.max_hp)

# ==============================================================================
# СИСТЕМА МИРА
# ==============================================================================

class Chunk:
    def __init__(self, cx: int, cy: int, seed: int):
        self.cx = cx
        self.cy = cy
        self.seed = seed
        self.biomes: Dict[Tuple[int, int], Biome] = {}
        self.resources: Dict[Tuple[int, int], List[Tuple[ResourceType, int]]] = {}
        self.entities: List[Entity] = []
        self.structures: List[Dict] = []
        self._generate()

    def _generate(self):
        noise = SimpleNoise(self.seed)
        size = CONFIG["CHUNK_SIZE"]
        offset_x = self.cx * size
        offset_y = self.cy * size

        for y in range(size):
            for x in range(size):
                wx, wy = offset_x + x, offset_y + y
                # Генерация биома
                n_val = noise.noise(wx / 1000, wy / 1000)
                n_detail = noise.noise(wx / 100, wy / 100)
                
                biome = Biome.PLAINS
                if n_val < -0.5:
                    biome = Biome.OCEAN
                elif n_val < -0.3:
                    biome = Biome.BEACH
                elif n_val > 0.6:
                    biome = Biome.MOUNTAIN
                elif n_val > 0.4:
                    biome = Biome.FOREST
                elif n_detail > 0.8:
                    biome = Biome.DESERT
                elif n_detail < -0.8:
                    biome = Biome.TUNDRA
                
                # Специальные зоны
                if (wx % 2000 < 100) and (wy % 2000 < 100):
                    biome = Biome.SERVER_HUB
                if random.random() < 0.001:
                    biome = Biome.RUINS

                self.biomes[(x, y)] = biome

                # Генерация ресурсов
                if random.random() < 0.1 and biome not in [Biome.OCEAN, Biome.SERVER_HUB]:
                    res_type = random.choice(list(ResourceType))
                    amount = random.randint(10, 100)
                    self.resources[(x, y)] = [(res_type, amount)]

class World:
    def __init__(self, seed: int):
        self.seed = seed
        self.chunks: Dict[Tuple[int, int], Chunk] = {}
        self.entities: Dict[str, Entity] = {}
        self.factions: Dict[str, Dict] = {}
        self.servers: Dict[str, Dict] = {}
        self.lock = threading.Lock()

    def get_chunk_coords(self, x: int, y: int) -> Tuple[int, int]:
        size = CONFIG["CHUNK_SIZE"]
        return (x // size, y // size)

    def get_chunk(self, x: int, y: int) -> Chunk:
        cx, cy = self.get_chunk_coords(x, y)
        if (cx, cy) not in self.chunks:
            self.chunks[(cx, cy)] = Chunk(cx, cy, self.seed + cx * cy)
        return self.chunks[(cx, cy)]

    def get_biome(self, x: int, y: int) -> Biome:
        chunk = self.get_chunk(x, y)
        lx = x % CONFIG["CHUNK_SIZE"]
        ly = y % CONFIG["CHUNK_SIZE"]
        return chunk.biomes.get((lx, ly), Biome.OCEAN)

    def get_resources(self, x: int, y: int) -> List[Tuple[ResourceType, int]]:
        chunk = self.get_chunk(x, y)
        lx = x % CONFIG["CHUNK_SIZE"]
        ly = y % CONFIG["CHUNK_SIZE"]
        return chunk.resources.get((lx, ly), [])

    def gather_resource(self, x: int, y: int, res_type: ResourceType) -> int:
        with self.lock:
            chunk = self.get_chunk(x, y)
            lx = x % CONFIG["CHUNK_SIZE"]
            ly = y % CONFIG["CHUNK_SIZE"]
            if (lx, ly) in chunk.resources:
                res_list = chunk.resources[(lx, ly)]
                for i, (rt, amount) in enumerate(res_list):
                    if rt == res_type:
                        gathered = min(amount, 10) # Лимит за раз
                        chunk.resources[(lx, ly)][i] = (rt, amount - gathered)
                        if chunk.resources[(lx, ly)][i][1] <= 0:
                            del chunk.resources[(lx, ly)]
                        return gathered
        return 0

    def add_entity(self, entity: Entity):
        with self.lock:
            self.entities[entity.id] = entity
            chunk = self.get_chunk(entity.pos.x, entity.pos.y)
            chunk.entities.append(entity)

    def remove_entity(self, eid: str):
        with self.lock:
            if eid in self.entities:
                entity = self.entities[eid]
                chunk = self.get_chunk(entity.pos.x, entity.pos.y)
                if entity in chunk.entities:
                    chunk.entities.remove(entity)
                del self.entities[eid]

    def create_server(self, owner_id: str, name: str, is_public: bool, is_temporary: bool) -> str:
        server_id = hashlib.md5(f"{owner_id}{time.time()}".encode()).hexdigest()[:8]
        self.servers[server_id] = {
            "id": server_id,
            "name": name,
            "owner": owner_id,
            "public": is_public,
            "temporary": is_temporary,
            "load": 0,
            "max_load": 1000 if not is_temporary else 100,
            "created_at": time.time(),
            "players": []
        }
        return server_id

# ==============================================================================
# МЕНЕДЖЕР ИГРЫ
# ==============================================================================

class Game:
    def __init__(self):
        self.world: Optional[World] = None
        self.player: Optional[Entity] = None
        self.running = False
        self.logs: deque = deque(maxlen=50)
        self.server_thread: Optional[threading.Thread] = None
        self.ai_thread: Optional[threading.Thread] = None
        self.turn = 0

    def log(self, message: str, color: str = "white"):
        timestamp = time.strftime("%H:%M:%S")
        self.logs.append(f"[{timestamp}] {CONFIG['COLORS'].get(color, '')}{message}{CONFIG['COLORS']['reset']}")

    def init_game(self, username: str, mode: str = "single"):
        seed = generate_world_seed()
        self.log(f"Генерация мира (Seed: {seed})...", "cyan")
        self.world = World(seed)
        
        # Создание игрока
        start_pos = Position(CONFIG["WORLD_SIZE"]//2, CONFIG["WORLD_SIZE"]//2)
        # Ищем безопасную точку
        while self.world.get_biome(start_pos.x, start_pos.y) == Biome.OCEAN:
            start_pos.x += random.randint(-10, 10)
            start_pos.y += random.randint(-10, 10)

        self.player = Entity("player_1", EntityType.PLAYER, start_pos, username)
        self.world.add_entity(self.player)
        self.log(f"Добро пожаловать, {username}! Вы появились в биоме {self.world.get_biome(start_pos.x, start_pos.y).value}.", "green")

        # Генерация ботов и фракций
        if mode == "single":
            self.generate_bots_and_factions()
        
        self.running = True
        self.start_background_threads()

    def generate_bots_and_factions(self):
        factions = ["Red Empire", "Blue Syndicate", "Green Collective", "Yellow Traders", "Purple Cult"]
        bot_names = ["Alex", "Maria", "John", "Sarah", "Victor", "Elena", "Bot-77", "Unit-X"]
        
        for fac in factions:
            self.world.factions[fac] = {"members": 0, "territory": 0, "hostile": False}
            
        for _ in range(50): # Создаем 50 ботов
            name = random.choice(bot_names) + str(random.randint(1, 100))
            x = random.randint(0, CONFIG["WORLD_SIZE"]-1)
            y = random.randint(0, CONFIG["WORLD_SIZE"]-1)
            if self.world.get_biome(x, y) != Biome.OCEAN:
                bot = Entity(f"bot_{random.randint(1000,9999)}", EntityType.BOT, Position(x, y), name)
                bot.faction = random.choice(list(self.world.factions.keys()))
                bot.ai.personality = random.choice(["neutral", "aggressive", "pacifist", "trader"])
                self.world.add_entity(bot)

    def start_background_threads(self):
        def ai_loop():
            while self.running:
                self.process_ai()
                time.sleep(CONFIG["AI_TICK_RATE"])

        def server_loop():
            while self.running:
                self.process_servers()
                time.sleep(CONFIG["SERVER_TICK_RATE"])

        self.ai_thread = threading.Thread(target=ai_loop, daemon=True)
        self.server_thread = threading.Thread(target=server_loop, daemon=True)
        self.ai_thread.start()
        self.server_thread.start()

    def process_ai(self):
        if not self.world: return
        # Обрабатываем только близких ботов для оптимизации
        if not self.player: return
        px, py = self.player.pos.x, self.player.pos.y
        
        bots_to_process = []
        for eid, entity in list(self.world.entities.items()):
            if entity.type == EntityType.BOT and entity.state != EntityState.DEAD:
                dist = entity.pos.distance_to(self.player.pos)
                if dist < 20: # Обрабатываем только тех, кто рядом
                    bots_to_process.append(entity)
        
        for bot in bots_to_process:
            if bot.state == EntityState.DEAD: continue
            
            goal = bot.ai.think(bot, {})
            
            if goal == "heal":
                if bot.stats.food > 10:
                    bot.stats.food -= 10
                    bot.heal(5)
            elif goal == "gather_food":
                # Простое движение к ресурсам (симуляция)
                if random.random() < 0.2:
                    bot.inventory.add(ResourceType.FOOD, 5)
            elif goal == "attack":
                # Атака игрока если рядом
                if bot.pos.distance_to(self.player.pos) == 1:
                    dmg = random.randint(1, 5)
                    self.player.take_damage(dmg)
                    self.log(f"{bot.name} атакует вас на {dmg} урона!", "red")
            
            # Случайное блуждание
            if random.random() < 0.3:
                dx = random.randint(-1, 1)
                dy = random.randint(-1, 1)
                bot.move(dx, dy, self.world)

    def process_servers(self):
        if not self.world: return
        for sid, server in list(self.world.servers.items()):
            if server["temporary"]:
                if time.time() - server["created_at"] > 3600: # 1 час жизни
                    del self.world.servers[sid]
                    self.log(f"Временный сервер {server['name']} закрыт.", "gray")
            else:
                # Симуляция нагрузки
                server["load"] = random.randint(0, server["max_load"])

    def player_action(self, action: str, args: Any = None):
        if not self.player or self.player.state == EntityState.DEAD:
            return

        if action == "move":
            dx, dy = args
            if self.player.move(dx, dy, self.world):
                self.turn += 1
                # Потребление ресурсов при движении
                self.player.stats.food -= 0.5
                self.player.stats.water -= 0.5
                # Случайные встречи
                if random.random() < 0.05:
                    self.encounter_event()
        
        elif action == "gather":
            res_list = self.world.get_resources(self.player.pos.x, self.player.pos.y)
            if res_list:
                res_type, _ = res_list[0]
                amount = self.world.gather_resource(self.player.pos.x, self.player.pos.y, res_type)
                if amount > 0:
                    self.player.inventory.add(res_type, amount)
                    self.log(f"Собрано: {amount} {res_type.value}", "green")
                else:
                    self.log("Ресурсы истощены в этой клетке.", "yellow")
            else:
                self.log("Здесь нет ресурсов.", "gray")
        
        elif action == "rest":
            self.player.stats.food -= 2
            self.player.stats.water -= 2
            self.player.heal(5)
            self.log("Вы отдохнули. HP восстановлено.", "cyan")
            self.turn += 5 # Отдых занимает время

        elif action == "craft":
            # Упрощенный крафт
            if self.player.inventory.get(ResourceType.WOOD) >= 5:
                self.player.inventory.remove(ResourceType.WOOD, 5)
                self.player.stats.max_hp += 5
                self.player.heal(5)
                self.log("Создано укрепление! Макс. HP увеличено.", "blue")
            else:
                self.log("Недостаточно дерева (нужно 5).", "red")

        elif action == "host_server":
            name = args.get("name", "MyServer")
            is_public = args.get("public", True)
            is_temp = args.get("temp", False)
            sid = self.world.create_server(self.player.id, name, is_public, is_temp)
            self.log(f"Сервер '{name}' запущен! ID: {sid}", "magenta")

        elif action == "status":
            self.show_status()

        # Проверка голода/жажды
        if self.player.stats.food <= 0 or self.player.stats.water <= 0:
            dmg = 2
            self.player.take_damage(dmg)
            self.log(f"Вы умираете от голода/жажды! -{dmg} HP", "red")

    def encounter_event(self):
        event_type = random.choice(["bandit", "merchant", "slave_hunter", "nothing"])
        if event_type == "bandit":
            self.log("На вас напали бандиты! Бой...", "red")
            dmg = random.randint(3, 8)
            self.player.take_damage(dmg)
        elif event_type == "merchant":
            self.log("Торговец предлагает обмен. (Функционал в разработке)", "yellow")
        elif event_type == "slave_hunter":
            if self.player.stats.hp < 10:
                self.player.is_slave = True
                self.player.state = EntityState.SLAVE
                self.log("Вас поймали и сделали рабом! Вы потеряли свободу.", "magenta")
            else:
                self.log("Охотники за рабами заметили вас, но вы смогли скрыться.", "cyan")

    def show_status(self):
        if not self.player: return
        p = self.player
        msg = (
            f"\n{CONFIG['COLORS']['bold']}=== СТАТУС ПЕРСОНАЖА ==={CONFIG['COLORS']['reset']}\n"
            f"HP: {p.stats.hp}/{p.stats.max_hp} | Еда: {p.stats.food:.1f} | Вода: {p.stats.water:.1f}\n"
            f"Уровень: {p.stats.level} | Опыт: {p.stats.exp}\n"
            f"Позиция: [{p.pos.x}, {p.pos.y}] | Биом: {self.world.get_biome(p.pos.x, p.pos.y).value}\n"
            f"Статус: {p.state.value} | Раб: {'Да' if p.is_slave else 'Нет'}\n"
            f"Инвентарь: " + ", ".join([f"{k.value}: {v}" for k, v in p.inventory.items.items()]) + "\n"
        )
        self.log(msg, "white")

    def render_minimap(self, radius: int = 5):
        if not self.player or not self.world:
            return ""
        
        output = []
        px, py = self.player.pos.x, self.player.pos.y
        
        # Заголовок
        output.append(f"{CONFIG['COLORS']['bold']}--- МИНИ-КАРТА ({radius*2+1}x{radius*2+1}) ---{CONFIG['COLORS']['reset']}")
        
        for dy in range(-radius, radius + 1):
            line = ""
            for dx in range(-radius, radius + 1):
                x, y = px + dx, py + dy
                
                if x == px and y == py:
                    line += f"{CONFIG['COLORS']['bg_green']}🧍{CONFIG['COLORS']['reset']}"
                    continue
                
                # Проверка границ
                if not (0 <= x < CONFIG["WORLD_SIZE"] and 0 <= y < CONFIG["WORLD_SIZE"]):
                    line += "⬛"
                    continue
                
                biome = self.world.get_biome(x, y)
                symbol = biome.value
                
                # Проверка на сущности
                has_entity = False
                for eid, ent in self.world.entities.items():
                    if ent.pos.x == x and ent.pos.y == y and ent != self.player:
                        if ent.type == EntityType.BOT:
                            symbol = "🤖"
                        elif ent.type == EntityType.CITY:
                            symbol = "🏰"
                        has_entity = True
                        break
                
                if not has_entity:
                    # Цвет фона в зависимости от биома
                    color_code = CONFIG['COLORS']['reset']
                    if biome == Biome.OCEAN: color_code = CONFIG['COLORS']['blue']
                    elif biome == Biome.FOREST: color_code = CONFIG['COLORS']['green']
                    elif biome == Biome.DESERT: color_code = CONFIG['COLORS']['yellow']
                    elif biome == Biome.MOUNTAIN: color_code = CONFIG['COLORS']['white']
                    elif biome == Biome.SERVER_HUB: color_code = CONFIG['COLORS']['magenta']
                    
                    line += f"{color_code}{symbol}{CONFIG['COLORS']['reset']}"
                else:
                    line += f"{CONFIG['COLORS']['red']}{symbol}{CONFIG['COLORS']['reset']}"
            
            output.append(line)
        
        return "\n".join(output)

    def render_interface(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"{CONFIG['COLORS']['bold']}╔══════════════════════════════════════════════════════════╗{CONFIG['COLORS']['reset']}")
        print(f"{CONFIG['COLORS']['bold']}║   EMPIRE OS: OMEGA PROTOCOL (AAAA+ EDITION)              ║{CONFIG['COLORS']['reset']}")
        print(f"{CONFIG['COLORS']['bold']}╚══════════════════════════════════════════════════════════╝{CONFIG['COLORS']['reset']}")
        
        # Статус бар
        if self.player:
            hp_pct = self.player.stats.hp / self.player.stats.max_hp
            bar_len = 20
            filled = int(bar_len * hp_pct)
            hp_bar = "█" * filled + "░" * (bar_len - filled)
            print(f"HP: [{hp_bar}] {self.player.stats.hp}/{self.player.stats.max_hp}")
            print(f"Координаты: {self.player.pos.x} : {self.player.pos.y} | Ход: {self.turn}")
        
        print("-" * 60)
        
        # Мини-карта
        if self.player:
            print(self.render_minimap())
        
        print("-" * 60)
        
        # Логи
        print(f"{CONFIG['COLORS']['bold']}ПОСЛЕДНИЕ СОБЫТИЯ:{CONFIG['COLORS']['reset']}")
        for log_entry in list(self.logs)[-8:]:
            print(log_entry)
        
        print("-" * 60)
        print("УПРАВЛЕНИЕ: [W]Вверх [S]Вниз [A]Влево [D]Вправо [G]Собрать [R]Отдых [C]Крафт [H]Хост [I]Инфо [Q]Выход")
        print("> ", end="", flush=True)

# ==============================================================================
# ГЛАВНЫЙ ЦИКЛ
# ==============================================================================

def main():
    game = Game()
    
    print("Загрузка EMPIRE OS...")
    time.sleep(1)
    
    name = input("Введите имя персонажа: ")
    if not name: name = "Stranger"
    
    game.init_game(name, mode="single")
    
    commands = {
        'w': (0, -1), 's': (0, 1), 'a': (-1, 0), 'd': (1, 0),
        'W': (0, -1), 'S': (0, 1), 'A': (-1, 0), 'D': (1, 0),
        'к': (0, -1), 'ы': (0, 1), 'ф': (-1, 0), 'в': (1, 0), # Раскладка ЙЦУКЕН
        'К': (0, -1), 'Ы': (0, 1), 'Ф': (-1, 0), 'В': (1, 0),
    }

    while game.running:
        game.render_interface()
        
        if game.player.state == EntityState.DEAD:
            print("\n💀 ВЫ ПОГИБЛИ. Игра окончена.")
            break
        
        try:
            cmd = input().strip().lower()
            
            if cmd == 'q':
                confirm = input("Вы уверены? (y/n): ")
                if confirm.lower() == 'y':
                    game.running = False
                continue
            
            if cmd in commands:
                game.player_action("move", commands[cmd])
            elif cmd == 'g':
                game.player_action("gather")
            elif cmd == 'r':
                game.player_action("rest")
            elif cmd == 'c':
                game.player_action("craft")
            elif cmd == 'h':
                s_name = input("Имя сервера: ")
                game.player_action("host_server", {"name": s_name, "public": True, "temp": False})
            elif cmd == 'i':
                game.player_action("status")
            elif cmd == '':
                continue # Просто обновить экран
            else:
                game.log(f"Неизвестная команда: {cmd}", "red")
                
        except KeyboardInterrupt:
            game.running = False
        except Exception as e:
            game.log(f"Ошибка: {e}", "red")

    print("Спасибо за игру в EMPIRE OS!")

if __name__ == "__main__":
    main()
