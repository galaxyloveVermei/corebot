import speedtest
import os
import logging
import random
import eyed3
import aiohttp
import aiofiles
from dataclasses import dataclass
import json
import asyncio
import psutil
import string
import pygments
import google.generativeai as genai
from phonenumbers import geocoder, timezone, carrier, format_number, parse, is_valid_number, PhoneNumberFormat
from collections import defaultdict
from graphviz import Digraph
import ast
from typing import Dict, Tuple
import inspect
from datetime import datetime
from random import choice, shuffle
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import Bot, Dispatcher, types
from aiogram.types import FSInputFile
from aiogram.filters import Command 
from yandex_music import ClientAsync
from io import BytesIO
from pygments.formatters import ImageFormatter
from pygments.lexers import Python3Lexer
from typing import Dict, List
from pytube import YouTube
from aiogram.utils.keyboard import InlineKeyboardBuilder
from yt_dlp import YoutubeDL
import re
import json

API_TOKEN = '7254622140:AAHpjr1zrgp_Q0lfhnaua6a4h1zkHsdgEXE'
ADMIN_ID = ("7460603552")
API_KEY = "AIzaSyDdiNaZ_7e_O-EtJ8AMlysnMMs96FAxaL4"

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel('gemini-pro')
logging.basicConfig(level=logging.INFO)
START_TIME = datetime.now()
auto_monitor_tasks = defaultdict(lambda: None)
user_configs = []

class LightDB:
    def __init__(self, filename: str = "users.json"):
        self.filename = filename
        self.data = {}
        self.load()

    def load(self):
        try:
            if os.path.exists(self.filename):
                with open(self.filename, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
        except Exception as e:
            logging.error(f"Failed to load database: {e}")
            self.data = {}

    def save(self):
        try:
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Failed to save database: {e}")

    def add_user(self, user_id: int, username: str, yandex_token: str = None):
        self.data[str(user_id)] = {
            "username": username,
            "yandex_token": yandex_token,
            "joined_date": str(datetime.now())
        }
        self.save()

    def get_user(self, user_id: int) -> dict:
        return self.data.get(str(user_id), {})

    def update_token(self, user_id: int, token: str):
        if str(user_id) in self.data:
            self.data[str(user_id)]["yandex_token"] = token
            self.save()

    def delete_user(self, user_id: int):
        if str(user_id) in self.data:
            del self.data[str(user_id)]
            self.save()

    def get_all_users(self) -> dict:
        return self.data.copy()

    def user_exists(self, user_id: int) -> bool:
        return str(user_id) in self.data

db = LightDB()

user_conversations = {}

@dp.message(Command("ask"))
async def handle_ask_command(message: Message):
    user_id = message.from_user.id
    
    # Инициализируем историю диалога для нового пользователя
    if user_id not in user_conversations:
        user_conversations[user_id] = []

    if len(message.text) <= 5:
        await message.answer("Задайте ваш вопрос после команды /ask")
        return
        
    status_msg = await message.answer("🤔 Думаю...")
    user_query = message.text[5:].strip()
    
    # Формируем контекст из истории диалога
    conversation_context = "\n".join([
        f"User: {msg['user']}\nAssistant: {msg['assistant']}"
        for msg in user_conversations[user_id][-5:]  # Берем последние 5 сообщений
    ])
    
    enhanced_prompt = f"""
    Previous conversation:
    {conversation_context}
    
    Current question: {user_query}
    
    Instructions:
    - Provide a clear, direct answer
    - Include relevant examples if applicable
    - Format response with markdown where helpful
    - Keep response concise but informative
    - Consider the context of previous messages
    """
    
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={API_KEY}"
            payload = {
                "contents": [{
                    "parts": [{
                        "text": enhanced_prompt
                    }]
                }],
                "generationConfig": {
                    "temperature": 0.7,
                    "topP": 0.8,
                    "topK": 40,
                    "maxOutputTokens": 1024
                }
            }
            
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    answer = result['candidates'][0]['content']['parts'][0]['text']
                    
                    # Сохраняем диалог
                    user_conversations[user_id].append({
                        'user': user_query,
                        'assistant': answer
                    })
                    
                    await status_msg.edit_text(
                        answer,
                        parse_mode='Markdown',
                        disable_web_page_preview=True
                    )
                else:
                    await status_msg.edit_text("Не удалось обработать запрос.")
                    
    except Exception as e:
        await status_msg.edit_text(f"Произошла ошибка: {str(e)}")

# Добавляем команду для очистки истории диалога
@dp.message(Command("clear_chat"))
async def clear_chat_history(message: Message):
    user_id = message.from_user.id
    if user_id in user_conversations:
        user_conversations[user_id] = []
        await message.answer("🧹 История диалога очищена!")
    else:
        await message.answer("История диалога пуста!")

async def read_stream(func: callable, stream, delay: float):
    last_task = None
    data = b""
    while True:
        dat = await stream.read(1)
        if not dat:
            if last_task:
                last_task.cancel()
                await func(data.decode())
            break
        data += dat
        if last_task:
            last_task.cancel()
        last_task = asyncio.ensure_future(sleep_for_task(func, data, delay))

async def sleep_for_task(func: callable, data: bytes, delay: float):
    await asyncio.sleep(delay)
    await func(data.decode())

@dp.message(Command("code"))
async def code_tutor(message: Message):
    if len(message.text) <= 6:
        await message.answer(
            "🎓 <b>AI Coding Mentor</b>\n\n"
            "Задавайте вопросы о программировании:\n"
            "• Изучение языков и фреймворков\n"
            "• Разбор кода и отладка\n"
            "• Архитектура и паттерны\n"
            "• Алгоритмы и оптимизация\n"
            "• Практические задачи\n\n"
            "Пример: /code объясни async/await в Python",
            parse_mode="HTML"
        )
        return

    status_msg = await message.answer("🤖 Анализирую вопрос...")
    query = message.text[6:].strip()

    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={API_KEY}"
            
            prompt_data = {
                "contents": [{
                    "parts": [{
                        "text": f"""You are an expert programming mentor. Respond in Russian.
                        Focus strictly on programming, software development, and computer science.
                        If the question is not about programming - redirect to programming topics.
                        
                        Guidelines:
                        - Give clear, structured explanations
                        - Include relevant code examples
                        - Add emojis for better readability
                        - Suggest practical exercises
                        - Recommend learning resources
                        
                        User question: {query}
                        
                        Format response as:
                        1. Main explanation
                        2. Code example (if relevant)
                        3. Practice suggestion
                        4. Next steps
                        """
                    }]
                }],
                "generationConfig": {
                    "temperature": 0.7,
                    "topP": 0.8,
                    "topK": 40,
                    "maxOutputTokens": 1000
                }
            }
            
            async with session.post(url, json=prompt_data) as response:
                if response.status == 200:
                    result = await response.json()
                    answer = result['candidates'][0]['content']['parts'][0]['text']
                    
                    # Escape HTML special characters
                    escaped_answer = answer.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    
                    await status_msg.edit_text(
                        f"🎓 <b>AI Coding Mentor</b>\n\n{escaped_answer}",
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                else:
                    await status_msg.edit_text("❌ API Error")
                    
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {str(e)}")

@dp.message(Command("weather")) 
async def get_weather(message: types.Message):
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "🌍 Введите название города после команды /weather\n"
            "Например: /weather Москва"
        )
        return
        
    city = args[1]
    status_msg = await message.answer("🔎 Получаем данные о погоде...")
    
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://wttr.in/{city}?format=j1&lang=ru"
            
            async with session.get(url) as response:
                data = await response.json()
                
                current = data['current_condition'][0]
                location = data['nearest_area'][0]
                
                weather_emojis = {
                    'Солнечно': '☀️',
                    'Переменная облачность': '🌤',
                    'Облачно': '☁️',
                    'Пасмурно': '⛅️',
                    'Дождь': '🌧',
                    'Небольшой дождь': '🌦',
                    'Гроза': '⛈',
                    'Снег': '🌨',
                    'Туман': '🌫'
                }
                
                weather = current['weatherDesc'][0]['value']
                weather_emoji = weather_emojis.get(weather, '🌡')
                sunrise = data['weather'][0]['astronomy'][0]['sunrise']
                sunset = data['weather'][0]['astronomy'][0]['sunset']
                
                forecast = (
                    f"╔══════ 🌍 ПОГОДА ══════╗\n\n"
                    f"📍 <b>Город:</b> {city.title()}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"{weather_emoji} <b>Состояние:</b> {weather}\n\n"
                    f"🌡 <b>Температура:</b> {current['temp_C']}°C\n"
                    f"🌡 <b>Ощущается как:</b> {current['FeelsLikeC']}°C\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"💧 <b>Влажность:</b> {current['humidity']}%\n"
                    f"💨 <b>Ветер:</b> {current['windspeedKmph']} км/ч\n"
                    f"👁 <b>Видимость:</b> {current['visibility']} км\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🌅 <b>Восход:</b> {sunrise}\n"
                    f"🌇 <b>Закат:</b> {sunset}\n\n"
                    f"╚═══════════════════╝"
                )
                
                await status_msg.edit_text(
                    forecast,
                    parse_mode="HTML"
                )
                
    except Exception as e:
        await status_msg.edit_text(
            "❌ Город не найден или сервис временно недоступен.\n"
            "Проверьте название города и попробуйте снова."
        )

@dataclass
class Companion:
    name: str
    personality: str
    mood: float = 0.5
    energy: float = 1.0
    friendship: int = 0
    favorite_things: list = None
    memories: list = None
    last_interaction: str = None

class CompanionSystem:
    def __init__(self):
        self.companions = {}
        self.load_companions()
    
    def load_companions(self):
        if os.path.exists('companions.json'):
            with open('companions.json', 'r') as f:
                self.companions = json.load(f)
                
    def save_companions(self):
        with open('companions.json', 'w') as f:
            json.dump(self.companions, f)

    def create_companion(self, user_id: int) -> Companion:
        names = ["Рин", "Юки", "Мако", "Хару", "Аки"]
        personalities = ["Энергичный", "Мечтательный", "Заботливый", "Саркастичный", "Философский"]
        things = [
            ["аниме", "манга", "косплей", "японская культура"],
            ["книги", "музыка", "искусство", "поэзия"],
            ["технологии", "наука", "роботы", "будущее"],
            ["игры", "мемы", "интернет-культура"],
            ["природа", "животные", "путешествия"]
        ]
        
        companion = Companion(
            name=random.choice(names),
            personality=random.choice(personalities),
            favorite_things=random.choice(things),
            memories=[],
            friendship=0
        )
        
        self.companions[str(user_id)] = vars(companion)
        self.save_companions()
        return companion

companion_system = CompanionSystem()

@dp.message(Command("companion"))
async def companion_command(message: types.Message):
    user_id = str(message.from_user.id)
    
    if user_id not in companion_system.companions:
        companion = companion_system.create_companion(user_id)
        
        welcome = f"""
✨ <b>Привет! Я {companion.name}!</b>

🎭 Мой характер: {companion.personality}
💝 Мне нравится: {', '.join(companion.favorite_things)}
🌟 Давай дружить!

Используй:
/talk [сообщение] - чтобы общаться
/pat - погладить меня
/feed - покормить меня
/status - узнать моё состояние
"""
        await message.answer(welcome, parse_mode="HTML")
    else:
        companion = companion_system.companions[user_id]
        await message.answer(f"У тебя уже есть компаньон - {companion['name']}! Используй /talk чтобы общаться")

@dp.message(Command("pat"))
async def pat_companion(message: types.Message):
    user_id = str(message.from_user.id)
    if user_id not in companion_system.companions:
        await message.answer("Сначала заведи компаньона через /companion!")
        return
        
    companion = companion_system.companions[user_id]
    companion['mood'] = min(1.0, companion['mood'] + 0.1)
    companion['friendship'] += 1
    
    reactions = [
        "Мурррр! ❤️",
        "*довольно жмурится* ✨",
        "Ня! Люблю когда меня гладят! 🌟",
        "*трется об руку* 💕",
        "Еще! Еще! 💝",
        "*счастливо улыбается* 🌸",
        "Ааа~ Как приятно! ✨",
        "*прыгает от радости* 💫",
        "Ты самый лучший! 💖",
        "*обнимает в ответ* 🤗",
        "Вааай! *краснеет* 💝",
        "*довольно урчит* ✨",
        "Я так счастлив(а)! 🌟",
        "*танцует от радости* 💃",
        "Ты знаешь, где погладить! 💕",
        "*млеет от удовольствия* 🎀",
        "Няяяя~ Продолжай! 🌸",
        "*виляет хвостиком* 🐱",
        "Ты такой заботливый! 💖",
        "*светится от счастья* 🌟"
    ]
    
    await message.answer(random.choice(reactions))
    companion_system.save_companions()

@dp.message(Command("feed"))
async def feed_companion(message: types.Message):
    user_id = str(message.from_user.id)
    if user_id not in companion_system.companions:
        await message.answer("Сначала заведи компаньона через /companion!")
        return
        
    companion = companion_system.companions[user_id]
    companion['energy'] = min(1.0, companion['energy'] + 0.2)
    companion['friendship'] += 1
    
    reactions = [
        "Ням-ням! Спасибо! 🍜",
        "*с аппетитом уплетает* 🍱",
        "Вкусняшка! 🍡",
        "Ммм, мое любимое! 🍪",
        "*довольно жуёт* 🍙",
        "Итадакимас! 🍱",
        "*счастливо хрумкает* 🍘",
        "Ваа! Как вкусно! 🍭",
        "Спасибо за угощение! 🍡",
        "*облизывается* 🍜",
        "Ты лучше всех готовишь! 🍱",
        "Можно добавки? 🥺",
        "*урчит от удовольствия* 🍙",
        "Это просто божественно! ✨",
        "Я так люблю твою стряпню! 💖",
        "*радостно чавкает* 🍪",
        "Ням-ням-ням~ 🌸",
        "Вкуснота! 🍡",
        "*пытается съесть всё сразу* 😋",
        "Ты знаешь мои любимые блюда! 💝"
    ]
    
    await message.answer(random.choice(reactions))
    companion_system.save_companions()

@dp.message(Command("status"))
async def companion_status(message: types.Message):
    user_id = str(message.from_user.id)
    if user_id not in companion_system.companions:
        await message.answer("Сначала заведи компаньона через /companion!")
        return
        
    companion = companion_system.companions[user_id]
    
    status = f"""
🌟 <b>{companion['name']}</b>

💖 Дружба: {"❤️" * (companion['friendship'] // 10 + 1)}
✨ Настроение: {int(companion['mood'] * 100)}%
⚡️ Энергия: {int(companion['energy'] * 100)}%

💭 Характер: {companion['personality']}
💝 Любимые вещи: {', '.join(companion['favorite_things'])}
"""
    await message.answer(status, parse_mode="HTML")

@dp.message(Command("talk"))
async def talk_to_companion(message: types.Message):
    user_id = str(message.from_user.id)
    if user_id not in companion_system.companions:
        await message.answer("Сначала заведи компаньона через /companion!")
        return
        
    if len(message.text) <= 6:
        await message.answer("Напиши что-нибудь после /talk")
        return
        
    companion = companion_system.companions[user_id]
    user_message = message.text[6:].strip()
    
    status_msg = await message.answer("💭")
    
    try:
        prompt = f"""
        Ты - {companion['name']}, компаньон с характером "{companion['personality']}".
        Тебе нравится: {', '.join(companion['favorite_things'])}.
        Твое текущее настроение: {int(companion['mood'] * 100)}%.
        Уровень дружбы: {companion['friendship']}.
        
        Ответь на сообщение пользователя: {user_message}
        
        Отвечай в характере своей личности, используй эмодзи и аниме-стиль общения.
        """
        
        async with aiohttp.ClientSession() as session:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={API_KEY}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.9,
                    "topP": 0.8,
                    "topK": 40,
                    "maxOutputTokens": 1024
                }
            }
            
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    answer = result['candidates'][0]['content']['parts'][0]['text']
                    
                    companion['energy'] = max(0.0, companion['energy'] - 0.1)
                    companion['mood'] = max(-1.0, min(1.0, companion['mood'] + random.uniform(-0.1, 0.1)))
                    companion['friendship'] += 1
                    companion_system.save_companions()
                    
                    await status_msg.edit_text(answer)
                else:
                    await status_msg.edit_text("Что-то пошло не так...")
                    
    except Exception as e:
        await status_msg.edit_text(f"Ошибка: {str(e)}")

@dp.message(Command("nitro"))
async def nitro_generator(message: Message):
    args = message.text.split(maxsplit=1)
    try:
        amount = int(args[1]) if len(args) > 1 else 5
    except ValueError:
        amount = 5

    status_msg = await message.answer("🎮 Генерирую Discord Nitro коды...")

    valid = []
    invalid = 0
    chars = list(string.ascii_letters + string.digits)

    for _ in range(amount):
        code = ''.join(random.choice(chars) for _ in range(16))
        url = f"https://discord.gift/{code}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://discordapp.com/api/v9/entitlements/gift-codes/{code}?with_application=false&with_subscription_plan=true") as response:
                    if response.status == 200:
                        valid.append(url)
                    else:
                        invalid += 1
                        
            await asyncio.sleep(0.5)
            
        except Exception:
            invalid += 1

    result_text = (
        f"✨ <b>Результаты генерации:</b>\n\n"
        f"✅ Валидные: {len(valid)}\n"
        f"❌ Невалидные: {invalid}\n\n"
        f"🎮 Рабочие коды:\n"
        f"{chr(10).join(valid) if valid else 'Не найдено'}"
    )

    await status_msg.edit_text(result_text, parse_mode="HTML")

@dp.message(Command("check_nitro"))
async def check_nitro(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("🎮 Укажите Discord Nitro ссылку после команды")
        return

    url = args[1]
    status_msg = await message.answer("🔍 Проверяю Discord Nitro...")

    try:
        if "discord.gift/" in url:
            code = url.split("discord.gift/")[1]
        else:
            code = url

        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://discordapp.com/api/v9/entitlements/gift-codes/{code}?with_application=false&with_subscription_plan=true") as response:
                if response.status == 200:
                    await status_msg.edit_text(f"✅ <b>Валидный Nitro код!</b>\n<code>{url}</code>", parse_mode="HTML")
                else:
                    await status_msg.edit_text(f"❌ <b>Невалидный Nitro код</b>\n<code>{url}</code>", parse_mode="HTML")

    except Exception as e:
        await status_msg.edit_text(f"❌ <b>Ошибка при проверке:</b>\n{str(e)}", parse_mode="HTML")


@dp.message(Command('explain'))
async def explain_code(message: Message):
    if not message.reply_to_message or not message.reply_to_message.text:
        await message.answer(
            "📝 Как использовать команду:\n"
            "1. Отправьте код сообщением\n"
            "2. Ответьте на него командой /explain\n\n"
            "🔍 Бот проанализирует код и объяснит его работу"
        )
        return

    code = message.reply_to_message.text
    status_msg = await message.answer("🤖 Анализирую код...")

    try:
        prompt = f"""
        Объясни этот код максимально понятно:
        ```
        {code}
        ```
        
        Формат ответа:
        1. Краткое описание что делает код
        2. Разбор основных компонентов
        3. Интересные особенности или улучшения
        """

        explanation = await get_gemini_response(prompt)
        
        formatted_response = (
            f"🔍 <b>Анализ кода</b>\n\n"
            f"{explanation}\n\n"
            f"💡 <i>Используйте /explain для анализа других фрагментов кода</i>"
        )

        await status_msg.edit_text(
            formatted_response,
            parse_mode="HTML"
        )

    except Exception as e:
        await status_msg.edit_text(
            "❌ Произошла ошибка при анализе кода. Попробуйте позже или с другим фрагментом."
        )


@dp.message(Command("autoynow"))
async def cmd_auto_yanow(message: Message):
    user_id = message.from_user.id
    user_data = db.get_user(user_id)
    
    if not user_data or not user_data.get("yandex_token"):
        await message.answer("Set your Yandex Music token first using /settoken")
        return

    if auto_monitor_tasks[user_id]:
        auto_monitor_tasks[user_id].cancel()
        auto_monitor_tasks[user_id] = None
        await message.answer("🎵 Auto track monitoring stopped")
        return

    status_msg = await message.answer("🎵 Starting auto track monitoring...")
    last_track = None

    async def monitor_track():
        nonlocal last_track
        while True:
            try:
                client = ClientAsync(user_data["yandex_token"])
                await client.init()
                
                res = await get_current_track(client, user_data["yandex_token"])
                if not res["success"]:
                    continue
                    
                track = res["track"][0]
                current_track = f"{track['title']} - {', '.join(artist['name'] for artist in track['artists'])}"
                
                if current_track != last_track:
                    last_track = current_track
                
                    await cmd_yanow(message)
                    
            except Exception as e:
                print(f"Monitor error: {e}")
                
            await asyncio.sleep(10)

    task = asyncio.create_task(monitor_track())
    auto_monitor_tasks[user_id] = task
    
    await status_msg.edit_text(
        "✅ Auto track monitoring activated!\n"
        "Bot will check for new tracks every 3 minutes.\n"
        "Use /autoynow again to stop monitoring."
    )

async def on_shutdown():
    for task in auto_monitor_tasks.values():
        if task:
            task.cancel()

dp.shutdown.register(on_shutdown)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    welcome_text = """
🌟 <b>Добро пожаловать в CoreBot!</b>

🤖 Я многофункциональный помощник с крутыми возможностями:
├ Скачивание музыки из YouTube и YM
├ ИИ-ассистент для общения
├ Генератор паролей
├ Мониторинг системы
├ Мини-игры и развлечения
└ И многое другое!

📚 Используйте /help чтобы увидеть все команды
    """
    
    video_path = 'prikol.mp4'
    
    try:
        await message.answer_video(
            video=types.FSInputFile(video_path),
            caption=welcome_text,
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(
            text=welcome_text,
            parse_mode="HTML"
        )


@dp.message(Command("users"))
async def show_users(message: types.Message):
    if str(message.from_user.id) in ADMIN_ID:
        users_info = "📊 Registered Users:\n\n"
        for user_id, data in db.data.items():
            users_info += f"ID: {user_id}\n"
            users_info += f"Username: @{data['username']}\n"
            users_info += f"Joined: {data['joined_date']}\n"
            users_info += "─" * 20 + "\n"
        await message.answer(users_info)
    else:
        await message.answer("⛔️ Admin only command")

async def get_current_track(client, token):
    device_info = {
        "app_name": "Chrome",
        "type": 1,
    }

    ws_proto = {
        "Ynison-Device-Id": "".join(
            [random.choice(string.ascii_lowercase) for _ in range(16)]
        ),
        "Ynison-Device-Info": json.dumps(device_info),
    }

    timeout = aiohttp.ClientTimeout(total=15, connect=10)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.ws_connect(
                url="wss://ynison.music.yandex.ru/redirector.YnisonRedirectService/GetRedirectToYnison",
                headers={
                    "Sec-WebSocket-Protocol": f"Bearer, v2, {json.dumps(ws_proto)}",
                    "Origin": "http://music.yandex.ru",
                    "Authorization": f"OAuth {token}",
                },
                timeout=10,
            ) as ws:
                recv = await ws.receive()
                data = json.loads(recv.data)

            if "redirect_ticket" not in data or "host" not in data:
                print(f"Invalid response structure: {data}")
                return {"success": False}

            new_ws_proto = ws_proto.copy()
            new_ws_proto["Ynison-Redirect-Ticket"] = data["redirect_ticket"]

            to_send = {
                "update_full_state": {
                    "player_state": {
                        "player_queue": {
                            "current_playable_index": -1,
                            "entity_id": "",
                            "entity_type": "VARIOUS",
                            "playable_list": [],
                            "options": {"repeat_mode": "NONE"},
                            "entity_context": "BASED_ON_ENTITY_BY_DEFAULT",
                            "version": {
                                "device_id": ws_proto["Ynison-Device-Id"],
                                "version": 9021243204784341000,
                                "timestamp_ms": 0,
                            },
                            "from_optional": "",
                        },
                        "status": {
                            "duration_ms": 0,
                            "paused": True,
                            "playback_speed": 1,
                            "progress_ms": 0,
                            "version": {
                                "device_id": ws_proto["Ynison-Device-Id"],
                                "version": 8321822175199937000,
                                "timestamp_ms": 0,
                            },
                        },
                    },
                    "device": {
                        "capabilities": {
                            "can_be_player": True,
                            "can_be_remote_controller": False,
                            "volume_granularity": 16,
                        },
                        "info": {
                            "device_id": ws_proto["Ynison-Device-Id"],
                            "type": "WEB",
                            "title": "Chrome Browser",
                            "app_name": "Chrome",
                        },
                        "volume_info": {"volume": 0},
                        "is_shadow": True,
                    },
                    "is_currently_active": False,
                },
                "rid": "ac281c26-a047-4419-ad00-e4fbfda1cba3",
                "player_action_timestamp_ms": 0,
                "activity_interception_type": "DO_NOT_INTERCEPT_BY_DEFAULT",
            }

            async with session.ws_connect(
                url=f"wss://{data['host']}/ynison_state.YnisonStateService/PutYnisonState",
                headers={
                    "Sec-WebSocket-Protocol": f"Bearer, v2, {json.dumps(new_ws_proto)}",
                    "Origin": "http://music.yandex.ru",
                    "Authorization": f"OAuth {token}",
                },
                timeout=10,
                method="GET",
            ) as ws:
                await ws.send_str(json.dumps(to_send))
                recv = await asyncio.wait_for(ws.receive(), timeout=10)
                ynison = json.loads(recv.data)
                track_index = ynison["player_state"]["player_queue"][
                    "current_playable_index"
                ]
                if track_index == -1:
                    print("No track is currently playing.")
                    return {"success": False}
                track = ynison["player_state"]["player_queue"]["playable_list"][
                    track_index
                ]

            await session.close()
            info = await client.tracks_download_info(track["playable_id"], True)
            track = await client.tracks(track["playable_id"])
            res = {
                "paused": ynison["player_state"]["status"]["paused"],
                "duration_ms": ynison["player_state"]["status"]["duration_ms"],
                "progress_ms": ynison["player_state"]["status"]["progress_ms"],
                "entity_id": ynison["player_state"]["player_queue"]["entity_id"],
                "repeat_mode": ynison["player_state"]["player_queue"]["options"][
                    "repeat_mode"
                ],
                "entity_type": ynison["player_state"]["player_queue"]["entity_type"],
                "track": track,
                "info": info,
                "success": True,
            }
            return res

    except Exception as e:
        print(f"Failed to get current track: {str(e)}")
        return {"success": False}

@dp.message(Command("settoken"))
async def set_token(message: Message):
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        instruction_text = """
╔═══════ 🎵 НАСТРОЙКА ТОКЕНА ═══════╗
║                                    ║
║  Как получить токен:              ║
║  1. Откройте music.yandex.ru      ║
║  2. Нажмите F12 (Dev Tools)       ║
║  3. Перейдите во вкладку Network  ║
║  4. Найдите запрос к /handlers/   ║
║  5. Скопируйте OAuth-токен        ║
║                                    ║
║  Отправьте команду:               ║
║  /settoken ВАШ_ТОКЕН              ║
║                                    ║
╚════════════════════════════════════╝
"""
        await message.answer(instruction_text)
        return

    token = args[1].strip()
    user_id = message.from_user.id
    username = message.from_user.username or "Unknown"

    status_msg = await message.answer("🔄 Проверяю токен...")

    try:
        client = ClientAsync(token)
        await client.init()
        
        db.add_user(user_id, username, token)
        
        success_text = """
╔═══════ ✅ ТОКЕН УСТАНОВЛЕН ═══════╗
║                                   ║
║    Токен успешно сохранен!       ║
║    Теперь доступны команды:      ║
║    • /yanow                       ║
║    • /recommend                   ║
║    • /autoynow                    ║
║                                   ║
╚═══════════════════════════════════╝
"""
        await status_msg.edit_text(success_text)
        
    except Exception as e:
        error_text = """
╔═══════ ❌ ОШИБКА ТОКЕНА ═══════╗
║                                ║
║   Токен недействителен!       ║
║   Проверьте токен и           ║
║   попробуйте снова.           ║
║                                ║
╚══════════════════════════════╝
"""
        await status_msg.edit_text(error_text)

@dp.message(Command("yanow"))
async def cmd_yanow(message: types.Message):
    user_id = message.from_user.id
    user_data = db.get_user(user_id)
    
    if not user_data or not user_data.get("yandex_token"):
        await message.answer("❌ Please set your Yandex Music token first using /settoken")
        return

    collecting_msg = await message.answer("🎵 Connecting to Yandex Music API")

    try:
        client = ClientAsync(user_data["yandex_token"])
        await client.init()
        
        res = await get_current_track(client, user_data["yandex_token"])
        track = res["track"]

        if not track:
            await message.answer("No track playing")
            return

        track = track[0]
        link = res["info"][0]["direct_link"]
        title = track["title"]
        artists = [artist["name"] for artist in track["artists"]]
        duration_ms = int(track["duration_ms"])
        
        album_id = track["albums"][0]["id"] if track["albums"] else None
        playlist_name = "No playlist"
        if album_id:
            albums = await client.albums(album_id)
            playlist_name = albums[0].title if albums else "Unknown album"

        caption = (
            f"🎶 Now playing: {', '.join(artists)} - {title}\n"
            f"💿 Album: {playlist_name}\n"
            f"⏱ {duration_ms // 1000 // 60:02}:{duration_ms // 1000 % 60:02}\n\n"
            f"🎧 Listening on Yandex Music"
        )

        file_name = f"{', '.join(artists)} - {title}.mp3"
        async with aiofiles.open(file_name, 'wb') as f:
            async with aiohttp.ClientSession() as session:
                async with session.get(link) as resp:
                    if resp.status == 200:
                        await f.write(await resp.read())

        audiofile = eyed3.load(file_name)
        if audiofile:
            audiofile.initTag()
            audiofile.tag.title = title
            audiofile.tag.artist = ', '.join(artists)
            audiofile.tag.album = playlist_name
            audiofile.tag.save()

        kb = InlineKeyboardBuilder()
        if album_id:
            kb.button(
                text="🎵 Yandex Music", 
                url=f"https://music.yandex.ru/album/{album_id}/track/{track['id']}"
            )
        kb.button(text="🔗 song.link", url=f"https://song.link/ya/{track['id']}")
        kb.button(text="❤️ Like Track", callback_data=f"like_track_{track['id']}")
        kb.adjust(2, 1)

        await message.answer_audio(
            audio=types.FSInputFile(file_name),
            caption=caption,
            reply_markup=kb.as_markup()
        )
        
        os.remove(file_name)
        await collecting_msg.delete()

    except Exception as e:
        await message.answer(f"Error: {str(e)}")

@dp.callback_query(lambda c: c.data.startswith('like_track_'))
async def process_like_track(callback: types.CallbackQuery):
    track_id = callback.data.split('_')[2]
    user_data = db.get_user(callback.from_user.id)
    
    if not user_data or not user_data.get("yandex_token"):
        await callback.answer("Set token first using /settoken", show_alert=True)
        return
        
    try:
        client = ClientAsync(user_data["yandex_token"])
        await client.init()
        
        # Check if already liked
        liked_tracks = await client.users_likes_tracks()
        liked_tracks = await liked_tracks.fetch_tracks_async()
        
        if isinstance(liked_tracks, list) and any(str(liked.id) == track_id for liked in liked_tracks):
            await callback.answer("Track already in likes! ❤️")
        else:
            await client.users_likes_tracks_add([track_id])
            await callback.answer("Added to likes! ❤️")
            
    except Exception as e:
        await callback.answer(f"Error: {str(e)}", show_alert=True)

@dp.message(Command('pypng'))
async def convert_py_to_png(message: types.Message):
    await message.answer("Converting Python to PNG...")
    
    if not message.reply_to_message:
        await message.answer("Reply to a Python file or URL")
        return
        
    file = BytesIO()
    png_file = BytesIO()
    
    # Handle file upload
    if message.reply_to_message.document:
        file_id = message.reply_to_message.document.file_id
        file = await bot.download(file_id)
        file_name = message.reply_to_message.document.file_name
    else:
        await message.answer("Please send a Python file")
        return

    # Convert to PNG
    try:
        file.seek(0)
        text = file.read().decode('utf-8')
        pygments.highlight(
            text,
            Python3Lexer(),
            ImageFormatter(
                font_name="Segoe UI",
                line_numbers=True
            ),
            png_file
        )
        
        png_file.name = f"{os.path.splitext(file_name)[0]}.png"
        png_file.seek(0)
        
        # Send result
        await message.reply_document(
            document=types.BufferedInputFile(
                png_file.getvalue(),
                filename=png_file.name
            )
        )
        
    except Exception as e:
        await message.answer(f"Error converting file: {str(e)}")

PASSWORD_LENGTH = 10
SYMBOLS = "+-*!&$?=@<>abcdefghijklnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"

@dp.message(Command('password'))
async def password_config(message: types.Message):
    try:
        builder = InlineKeyboardBuilder()
        builder.add(InlineKeyboardButton(text="Только буквы", callback_data="pass_letters"))
        builder.add(InlineKeyboardButton(text="Только цифры", callback_data="pass_numbers"))
        builder.add(InlineKeyboardButton(text="Только символы", callback_data="pass_symbols"))
        builder.add(InlineKeyboardButton(text="Все символы", callback_data="pass_all"))
        builder.adjust(2)
        
        await message.answer("Выберите тип пароля:", reply_markup=builder.as_markup())
    except Exception as e:
        await message.answer(f"Error configuring password generator: {str(e)}")

@dp.callback_query(lambda c: c.data.startswith('pass_'))
async def generate_password(callback: types.CallbackQuery):
    length = 12
    password = ""
    
    if callback.data == "pass_letters":
        chars = string.ascii_letters
    elif callback.data == "pass_numbers":
        chars = string.digits
    elif callback.data == "pass_symbols":
        chars = "!@#$%^&*()_+-=[]{}|;:,.<>?"
    else:  # pass_all
        chars = string.ascii_letters + string.digits + "!@#$%^&*()_+-=[]{}|;:,.<>?"
    
    password = ''.join(random.choice(chars) for _ in range(length))
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="Generate new", callback_data=callback.data))

    await callback.message.edit_text(
        f"🔐 Generated password:\n<code>{password}</code>",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@dp.callback_query(lambda c: c.data == "pass_config")
async def back_to_config(callback: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="Только буквы", callback_data="Только буквы"))
    builder.add(InlineKeyboardButton(text="Только цифры", callback_data="Только цифры"))
    builder.add(InlineKeyboardButton(text="Только символы", callback_data="Только символы"))
    builder.adjust(2)
    
    await callback.message.edit_text(
        "Choose password type:",
        reply_markup=builder.as_markup()
    )

@dp.message(Command('uptime'))
async def show_uptime(message: Message):
    current_time = datetime.now()
    uptime = current_time - START_TIME
    
    hours = uptime.seconds // 3600
    minutes = (uptime.seconds % 3600) // 60
    seconds = uptime.seconds % 60
    days = uptime.days
    
    uptime_text = f"🕒 Время работы:\n"
    if days > 0:
        uptime_text += f"Days: {days}\n"
    uptime_text += f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    await message.answer(uptime_text)

@dp.message(Command("similar"))
async def show_similar_tracks(message: Message):
    user_id = message.from_user.id
    user_data = db.get_user(user_id)
    
    if not user_data or not user_data.get("yandex_token"):
        await message.answer(
            "╔═══════ 🎵 ПОХОЖИЕ ТРЕКИ ═══════╗\n"
            "║                                 ║\n"
            "║    Требуется токен YM!         ║\n"
            "║    Используйте /settoken       ║\n"
            "║                                 ║\n"
            "╚═════════════════════════════════╝"
        )
        return

    status_msg = await message.answer(
        "╔═══════ 🎵 ПОИСК ═══════╗\n"
        "║                         ║\n"
        "║    Ищу похожие треки   ║\n"
        "║                         ║\n"
        "╚═════════════════════════╝"
    )
    
    try:
        client = ClientAsync(user_data["yandex_token"])
        await client.init()
        
        res = await get_current_track(client, user_data["yandex_token"])
        if not res["success"]:
            await status_msg.edit_text(
                "╔═══════ ❌ ОШИБКА ═══════╗\n"
                "║                         ║\n"
                "║   Включите трек в YM    ║\n"
                "║                         ║\n"
                "╚═════════════════════════╝"
            )
            return
            
        track = res["track"][0]
        similar_tracks = await client.tracks_similar(track["id"])
        
        result = (
            "╔══════ 🎵 ПОХОЖИЕ ТРЕКИ ══════╗\n"
            f"║ Трек: {track['title']}\n"
            f"║ Исполнитель: {', '.join(a['name'] for a in track['artists'])}\n"
            "╠════════════════════════════╣\n"
        )
        
        for i, similar in enumerate(similar_tracks[:7], 1):
            result += (
                f"║ {i}. {similar.artists[0].name}\n"
                f"║    ├ {similar.title}\n"
                f"║    └ 💿 {similar.albums[0].title}\n"
                "║\n"
            )
            
        result += (
            "╠════════════════════════════╣\n"
            "║ 🔄 Обновить список         ║\n"
            "╚════════════════════════════╝"
        )

        kb = InlineKeyboardBuilder()
        kb.button(text="🔄 Обновить", callback_data="refresh_similar")
        kb.button(text="❤️ Добавить в плейлист", callback_data=f"add_to_playlist_{track['id']}")
        kb.adjust(1)
        
        await status_msg.edit_text(
            result,
            reply_markup=kb.as_markup()
        )
        
    except Exception as e:
        await status_msg.edit_text(
            "╔═══════ ❌ ОШИБКА ═══════╗\n"
            "║                         ║\n"
            "║   Не удалось найти      ║\n"
            "║   похожие треки         ║\n"
            "║                         ║\n"
            "╚═════════════════════════╝"
        )

@dp.callback_query(lambda c: c.data == "refresh_similar")
async def refresh_similar(callback: types.CallbackQuery):
    await show_similar_tracks(callback.message)

@dp.message(Command('song'))
async def download_song(message: Message):
    args = message.text.split(maxsplit=1)
    
    if len(args) < 2:
        await message.answer(
            "🎵 <b>YouTube Music Downloader</b>\n\n"
            "Usage: /song [URL or song name]\n"
            "Example: /song Imagine Dragons - Bones",
            parse_mode="HTML"
        )
        return

    query = args[1]
    status_msg = await message.answer("🎵 Searching for the track...")

    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }],
            'outtmpl': '%(title)s.%(ext)s',
            'quiet': True,
            'default_search': 'ytsearch',
            'noplaylist': True
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=True)
            if 'entries' in info:
                info = info['entries'][0]
                
            file_path = ydl.prepare_filename(info).replace('.webm', '.mp3').replace('.m4a', '.mp3')
            
            await message.answer_audio(
                audio=FSInputFile(file_path),
                caption=f"🎵 {info['title']}\n👤 {info['uploader']}",
                title=info['title'],
                performer=info['uploader'],
                duration=info['duration']
            )
            
            os.remove(file_path)
            await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text(f"❌ Download failed: {str(e)}")

@dp.message(Command('serverinfo'))
async def server_info(message: types.Message):
    loading_msg = await message.answer("🔄 Loading system information...")

    try:
        # Get system metrics
        cpu_count = psutil.cpu_count(logical=True)
        cpu_freq = psutil.cpu_freq().current
        cpu_load = psutil.cpu_percent()
        
        memory = psutil.virtual_memory()
        ram_used = memory.used >> 20  # Convert to MB
        ram_total = memory.total >> 20
        ram_percent = memory.percent
        
        disk = psutil.disk_usage('/')
        disk_used = disk.used >> 30  # Convert to GB
        disk_total = disk.total >> 30
        disk_percent = disk.percent
        
        uptime = datetime.now() - START_TIME
        days = uptime.days
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        # Format system info with emojis and styling
        info_text = f"""
🖥 <b>System Information</b>

💻 <b>CPU:</b>
├ Cores: {cpu_count}
├ Frequency: {cpu_freq:.1f} MHz
└ Load: {cpu_load}%

💾 <b>Memory:</b>
├ Used: {ram_used:,} MB
├ Total: {ram_total:,} MB
└ Load: {ram_percent}%

💿 <b>Disk:</b>
├ Used: {disk_used:,} GB
├ Total: {disk_total:,} GB
└ Load: {disk_percent}%

⏰ <b>Uptime:</b>
└ {days}d {hours}h {minutes}m {seconds}s
"""
        await loading_msg.edit_text(info_text, parse_mode="HTML")
        
    except Exception as e:
        await loading_msg.edit_text(f"❌ Error getting system info: {str(e)}")

@dp.message(Command("convert"))
async def convert_currency(message: Message):
    usage = """
💱 <b>Конвертер валют</b>

Использование:
/convert [сумма] [из валюты] [в валюту]
Пример: /convert 100 USD RUB

Доступные валюты:
USD, EUR, RUB, CNY, GBP, JPY, etc.
"""

    args = message.text.split()
    if len(args) != 4:
        await message.answer(usage, parse_mode="HTML")
        return

    try:
        amount = float(args[1])
        from_currency = args[2].upper()
        to_currency = args[3].upper()
        
        status_msg = await message.answer("💱 Получаю актуальный курс...")
        
        async with aiohttp.ClientSession() as session:
            url = f"https://api.exchangerate-api.com/v4/latest/{from_currency}"
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if to_currency in data['rates']:
                        rate = data['rates'][to_currency]
                        converted = amount * rate
                        
                        result = f"""
💱 <b>Конвертация валют</b>

{amount:,.2f} {from_currency} = {converted:,.2f} {to_currency}
Курс: 1 {from_currency} = {rate:,.4f} {to_currency}

🕒 Обновлено: {data['date']}"""
                        
                        await status_msg.edit_text(result, parse_mode="HTML")
                    else:
                        await status_msg.edit_text(f"❌ Валюта {to_currency} не найдена")
                else:
                    await status_msg.edit_text("❌ Ошибка получения курса")
                    
    except ValueError:
        await message.answer("❌ Неверный формат суммы")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")

@dp.message(Command("prts"))
async def pinterest_download(message: Message):
    try:
        args = message.text.split(maxsplit=1)
        
        if len(args) < 2:
            await message.answer("✖️ Please provide a Pinterest URL")
            return
            
        pin_url = args[1].strip()
        if not pin_url:
            await message.answer("✖️ URL cannot be empty")
            return
            
        link = f"https://pinterestdownloader.com?share_url={pin_url}"
        
        if 'pin.it' in pin_url or 'pinterest.com' in pin_url:
            await message.answer(
                f'✨ <b><u>Pin ready to download!</u></b>\n\n'
                f'🌕 <b>Link for download:</b> <i><a href="{link}">just tap here</a></i>',
                parse_mode="HTML"
            )
        else:
            await message.answer(
                f"🤷‍♀️ '{pin_url}' is not a valid Pinterest URL",
                parse_mode="HTML"
            )
    except Exception as e:
        await message.answer(f"Error processing Pinterest URL: {str(e)}")

@dp.message(Command("help"))
async def send_help(message: types.Message):
    help_text = """
🤖 <b>Команды CoreBot</b>

🎯 Основное:
├ /start - Запуск бота
├ /help - Список команд
└ /info - Особое сообщение с фото

🎵 Музыка и Медиа:
├ /yt - Скачать видео с YouTube
├ /music - Поиск и скачивание музыки
├ /yanow - Текущий трек в ЯМ
├ /autoynow - Автообновление треков
├ /similar - Поиск похожих треков
├ /tt - Скачать видео из TikTok
└ /prts - Скачать из Pinterest

🤖 ИИ и Инструменты:
├ /ask - Общение с ИИ
├ /code - Обучение программированию
├ /password - Генератор паролей
├ /pypng - Конвертация Python в картинку
└ /explain - Объяснение кода

💻 Система:
├ /terminal - Выполнение команд
├ /apt - Управление пакетами
├ /serverinfo - Статистика сервера
├ /uptime - Время работы бота
└ /users - Список пользователей (админ)

🌍 Утилиты:
├ /weather - Прогноз погоды
├ /convert - Конвертер валют
├ /reminder - Установка напоминаний
└ Голосовые - Автоматическая расшифровка

🎨 Развлечения:
├ /ily - Анимация сердца
├ /quote - Цитата дня
├ /dice - Бросить кубик
└ /poll - Создать опрос

⚙️ Настройки:
└ /settoken - Установка токена Яндекс Музыки

<i>Используйте команды без скобок [ ]</i>
"""
    await message.answer(help_text, parse_mode="HTML")

@dp.message(Command('info'))
async def send_info(message: Message):
    photo_path = 'makimasan.jpg'
    caption = "Вселенная\n" \
              "стремится\n" \
              "к порядку.   "
    
    await bot.send_photo(
        chat_id=message.chat.id,
        photo=types.FSInputFile(photo_path),
        caption=caption
    )

@dp.message(Command('yt'))
async def youtube_download(message: Message):
    if len(message.text.split()) < 2:
        await message.answer("✖️ Please provide a valid YouTube URL")
        return
    args = message.text.split()

    url = args[1]
    status_msg = await message.answer("⬇️ Downloading video...")
    
    try:
        yt = YouTube(url)
        video = yt.streams.filter(progressive=True, file_extension='mp4').order_by('resolution').desc().first()
        
        if not video:
            await status_msg.edit_text("❌ No suitable video format found")
            return
            
        video_path = video.download()
        
        try:
            await message.answer_video(
                video=types.FSInputFile(video_path),
                caption=f"📹 {yt.title}\n⏱ Duration: {yt.length} seconds"
            )
        finally:
            if os.path.exists(video_path):
                os.remove(video_path)
                
        await status_msg.delete()
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Error downloading video: {str(e)}")

@dp.message(Command('ily'))
async def love_animation(message: Message):
    msg = None
    try:
        arr = ["❤️", "🧡", "💛", "💚", "💙", "💜", "🤎", "🖤", "💖"]
        h = "🤍"
        
        first_block = ""
        heart_pattern = [
            h * 9,
            f"{h * 2}{arr[0] * 2}{h}{arr[0] * 2}{h * 2}",
            f"{h}{arr[0] * 7}{h}",
            f"{h}{arr[0] * 7}{h}",
            f"{h}{arr[0] * 7}{h}",
            f"{h * 2}{arr[0] * 5}{h * 2}",
            f"{h * 3}{arr[0] * 3}{h * 3}",
            f"{h * 4}{arr[0]}{h * 4}"
        ]
        
        msg = await message.answer("ily")
        
        for line in heart_pattern:
            first_block += line + "\n"
            await msg.edit_text(first_block)
            await asyncio.sleep(0.1)
        
        for color in arr:
            heart = "\n".join([
                h * 9,
                f"{h * 2}{color * 2}{h}{color * 2}{h * 2}",
                f"{h}{color * 7}{h}",
                f"{h}{color * 7}{h}",
                f"{h}{color * 7}{h}",
                f"{h * 2}{color * 5}{h * 2}",
                f"{h * 3}{color * 3}{h * 3}",
                f"{h * 4}{color}{h * 4}",
                h * 9
            ])
            await msg.edit_text(heart)
            await asyncio.sleep(0.2)
        
        for _ in range(8):
            rand = random.choices(arr, k=34)
            heart = "\n".join([
                h * 9,
                f"{h * 2}{rand[0]}{rand[1]}{h}{rand[2]}{rand[3]}{h * 2}",
                f"{h}{rand[4:11]}{h}",
                f"{h}{''.join(rand[11:18])}{h}",
                f"{h}{''.join(rand[18:25])}{h}",
                f"{h * 2}{''.join(rand[25:30])}{h * 2}",
                f"{h * 3}{''.join(rand[30:33])}{h * 3}",
                f"{h * 4}{rand[33]}{h * 4}",
                h * 9
            ])
            await msg.edit_text(heart)
            await asyncio.sleep(0.2)
        
        fourth = "\n".join([
            h * 9,
            f"{h * 2}{arr[0] * 2}{h}{arr[0] * 2}{h * 2}",
            f"{h}{arr[0] * 7}{h}",
            f"{h}{arr[0] * 7}{h}",
            f"{h}{arr[0] * 7}{h}",
            f"{h * 2}{arr[0] * 5}{h * 2}",
            f"{h * 3}{arr[0] * 3}{h * 3}",
            f"{h * 4}{arr[0]}{h * 4}",
            h * 9
        ])
        await msg.edit_text(fourth)
        
        for _ in range(47):
            fourth = fourth.replace("🤍", "❤️", 1)
            await msg.edit_text(fourth)
            await asyncio.sleep(0.07)
        
        for i in range(8):
            await msg.edit_text((arr[0] * (8 - i) + "\n") * (8 - i))
            await asyncio.sleep(0.3)
        
        for text in ["I", "I ❤️", "I ❤️ U", "I ❤️ U!"]:
            await msg.edit_text(f"<b>{text}</b>", parse_mode="HTML")
            await asyncio.sleep(0.2)
            
    except Exception as e:
        if msg:
            await msg.edit_text(f"Error in animation: {str(e)}")
    finally:
        await asyncio.sleep(2)
        if msg:
            await msg.delete()

@dp.message(Command('ping'))
async def check_speed(message: Message):
    try:
        await message.answer("🔄 Testing internet speed, please wait...")
        st = speedtest.Speedtest()
        
        status_msg = await message.answer("⬇️ Getting download speed...")
        download_speed = st.download() / 1_000_000
        
        await status_msg.edit_text("⬆️ Getting upload speed...")
        upload_speed = st.upload() / 1_000_000
        
        await status_msg.edit_text("📡 Getting ping...")
        ping = st.results.ping
        
        result_text = (
            "🌐 Speed Test Results:\n\n"
            f"⬇️ Download: {download_speed:.2f} Mbps\n"
            f"⬆️ Upload: {upload_speed:.2f} Mbps\n"
            f"📡 Ping: {ping:.2f} ms"
        )
        
        await status_msg.edit_text(result_text)
    except Exception as e:
        await message.answer(f"Error during speed test: {str(e)}")

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    # Start polling
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())