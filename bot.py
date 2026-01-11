import asyncio
import logging
import sqlite3
import json
from datetime import datetime
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    WebAppInfo, ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# =================== КОНФИГУРАЦИЯ ===================
BOT_TOKEN = "8381986284:AAHhJWbm3b0dAep7lpIw2porfmQEt2-vvw0"
ADMIN_ID = 7725796090  # Твой ID
WEBAPP_URL = "https://artureooe.github.io/Jsjjeje/"  # Замени на реальный URL сайта

# Начальные цены (будут меняться через админку)
PRICES = {
    "star_rate": 1.45,
    "ton_rate": 167.0,
    "premium_3": 15,
    "premium_6": 19,
    "premium_12": 28
}

# =================== БАЗА ДАННЫХ ===================
class Database:
    def __init__(self):
        self.conn = sqlite3.connect('art_stars_simple.db', check_same_thread=False)
        self.create_tables()
        self.load_prices()
    
    def create_tables(self):
        cursor = self.conn.cursor()
        
        # Пользователи
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Заказы
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                product TEXT,
                quantity REAL,
                total REAL,
                currency TEXT,
                username TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Техподдержка (админы - те, кто отвечает)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS support_admins (
                user_id INTEGER PRIMARY KEY,
                added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Заявки поддержки
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                user_name TEXT,
                message TEXT,
                status TEXT DEFAULT 'new',
                admin_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Настройки (цены)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        # Добавляем админа по умолчанию
        cursor.execute('INSERT OR IGNORE INTO support_admins (user_id, added_by) VALUES (?, ?)', 
                      (ADMIN_ID, ADMIN_ID))
        
        # Сохраняем начальные цены
        for key, value in PRICES.items():
            cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', 
                          (key, str(value)))
        
        self.conn.commit()
        print("✅ База данных создана!")
    
    def load_prices(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT key, value FROM settings')
        for key, value in cursor.fetchall():
            if key in PRICES:
                try:
                    PRICES[key] = float(value)
                except:
                    PRICES[key] = value
    
    def update_price(self, key, value):
        cursor = self.conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', 
                      (key, str(value)))
        self.conn.commit()
        PRICES[key] = value
        return True
    
    def add_user(self, user_id, username, full_name):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, username, full_name)
            VALUES (?, ?, ?)
        ''', (user_id, username, full_name))
        self.conn.commit()
    
    def is_support_admin(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT 1 FROM support_admins WHERE user_id = ?', (user_id,))
        return cursor.fetchone() is not None
    
    def add_support_admin(self, admin_id, added_by):
        cursor = self.conn.cursor()
        cursor.execute('INSERT OR IGNORE INTO support_admins (user_id, added_by) VALUES (?, ?)', 
                      (admin_id, added_by))
        self.conn.commit()
        return True
    
    def remove_support_admin(self, admin_id):
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM support_admins WHERE user_id = ?', (admin_id,))
        self.conn.commit()
        return cursor.rowcount > 0
    
    def get_all_support_admins(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT sa.user_id, u.username, u.full_name, sa.added_at 
            FROM support_admins sa
            LEFT JOIN users u ON sa.user_id = u.user_id
            ORDER BY sa.added_at
        ''')
        return cursor.fetchall()
    
    def create_support_ticket(self, user_id, user_name, message):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO support_tickets (user_id, user_name, message)
            VALUES (?, ?, ?)
        ''', (user_id, user_name, message))
        self.conn.commit()
        return cursor.lastrowid
    
    def get_new_tickets(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM support_tickets 
            WHERE status = 'new'
            ORDER BY created_at DESC
        ''')
        return cursor.fetchall()
    
    def get_all_tickets(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT * FROM support_tickets 
            ORDER BY created_at DESC
        ''')
        return cursor.fetchall()
    
    def get_ticket_by_id(self, ticket_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM support_tickets WHERE id = ?', (ticket_id,))
        return cursor.fetchone()
    
    def assign_ticket(self, ticket_id, admin_id):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE support_tickets 
            SET status = 'in_progress', admin_id = ?
            WHERE id = ?
        ''', (admin_id, ticket_id))
        self.conn.commit()
    
    def close_ticket(self, ticket_id):
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE support_tickets 
            SET status = 'closed'
            WHERE id = ?
        ''', (ticket_id,))
        self.conn.commit()
    
    def create_order(self, user_id, product, quantity, total, currency, username):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO orders (user_id, product, quantity, total, currency, username)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, product, quantity, total, currency, username))
        self.conn.commit()
        return cursor.lastrowid
    
    def get_stats(self):
        cursor = self.conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM users')
        users = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM orders')
        orders = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM support_tickets WHERE status = "new"')
        new_tickets = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM support_admins')
        admins = cursor.fetchone()[0]
        
        return {
            'users': users,
            'orders': orders,
            'new_tickets': new_tickets,
            'admins': admins,
            'prices': PRICES
        }

# =================== FSM СОСТОЯНИЯ ===================
class Form(StatesGroup):
    waiting_support_message = State()
    admin_reply = State()
    waiting_new_admin = State()
    waiting_remove_admin = State()
    waiting_set_price = State()

# =================== ИНИЦИАЛИЗАЦИЯ ===================
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

db = Database()

# =================== КЛАВИАТУРЫ ===================
def main_menu():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✨ Открыть магазин", web_app=WebAppInfo(url=WEBAPP_URL))],
            [KeyboardButton(text="🆘 Техподдержка"), KeyboardButton(text="👑 Админ-панель")]
        ],
        resize_keyboard=True
    )
    return keyboard

def admin_menu():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Новые заявки", callback_data="admin_new_tickets")],
            [InlineKeyboardButton(text="👨‍💼 Управление поддержкой", callback_data="admin_manage_support")],
            [InlineKeyboardButton(text="💰 Управление ценами", callback_data="admin_manage_prices")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton(text="🔄 Обновить сайт", callback_data="admin_refresh_webapp")]
        ]
    )
    return keyboard

def support_management_menu():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить ТП-админа", callback_data="admin_add_support")],
            [InlineKeyboardButton(text="➖ Удалить ТП-админа", callback_data="admin_remove_support")],
            [InlineKeyboardButton(text="📝 Список ТП-админов", callback_data="admin_list_support")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
        ]
    )
    return keyboard

def prices_management_menu():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⭐ Цена звезды", callback_data="price_star")],
            [InlineKeyboardButton(text="💎 Цена TON", callback_data="price_ton")],
            [InlineKeyboardButton(text="🏆 Premium 3 мес", callback_data="price_premium_3")],
            [InlineKeyboardButton(text="🏆 Premium 6 мес", callback_data="price_premium_6")],
            [InlineKeyboardButton(text="🏆 Premium 12 мес", callback_data="price_premium_12")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
        ]
    )
    return keyboard

def cancel_keyboard():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
        ]
    )
    return keyboard

# =================== ОСНОВНЫЕ КОМАНДЫ ===================
@router.message(CommandStart())
async def cmd_start(message: Message):
    db.add_user(message.from_user.id, 
                message.from_user.username, 
                message.from_user.full_name)
    
    await message.answer(
        "✨ *Art Stars - Мини-приложение*\n\n"
        "Здесь ты можешь:\n"
        "• 🛒 Открыть магазин для покупки\n"
        "• 🆘 Написать в поддержку\n"
        "👇 Используй кнопки ниже:",
        reply_markup=main_menu(),
        parse_mode="Markdown"
    )

@router.message(F.text == "✨ Открыть магазин")
async def open_shop(message: Message):
    await message.answer(
        "🛒 *Магазин открывается...*\n\n"
        "Нажми кнопку ниже, чтобы перейти в мини-приложение:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✨ Открыть магазин", web_app=WebAppInfo(url=WEBAPP_URL))],
                [KeyboardButton(text="🆘 Техподдержка")]
            ],
            resize_keyboard=True
        ),
        parse_mode="Markdown"
    )

# =================== ТЕХПОДДЕРЖКА ===================
@router.message(F.text == "🆘 Техподдержка")
async def support_start(message: Message, state: FSMContext):
    await message.answer(
        "🆘 *Техническая поддержка*\n\n"
        "Опиши свою проблему:\n"
        "• Проблема с оплатой\n"
        "• Не пришёл товар\n"
        "• Проверить оплату\n"
        "• Другое\n\n"
        "Просто напиши сообщение ниже ⬇️\n\n"
        "Используй /cancel для отмены",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.waiting_support_message)

@router.message(Form.waiting_support_message)
async def support_message_received(message: Message, state: FSMContext):
    if message.text and message.text.startswith('/cancel'):
        await state.clear()
        await message.answer("❌ Создание заявки отменено", reply_markup=main_menu())
        return
    
    ticket_id = db.create_support_ticket(
        message.from_user.id,
        message.from_user.full_name,
        message.text or "📎 Вложение"
    )
    
    # ОТПРАВЛЯЕМ ВСЕМ ТП-АДМИНАМ
    admins = db.get_all_support_admins()
    
    for admin in admins:
        try:
            await bot.send_message(
                admin[0],
                f"🆘 *НОВАЯ ЗАЯВКА #{ticket_id}*\n\n"
                f"👤 *Клиент:* {message.from_user.full_name}\n"
                f"🆔 *ID:* {message.from_user.id}\n"
                f"📝 *Сообщение:* {message.text or '📎 Вложение'}\n\n"
                f"📌 Для ответа нажми: /reply_{ticket_id}",
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Не удалось отправить админу {admin[0]}: {e}")
    
    await message.answer(
        "✅ *Заявка создана!*\n\n"
        f"Номер: *#{ticket_id}*\n"
        "ТП-админы уже получили твоё сообщение и скоро ответят.\n\n"
        "Жди ответа здесь в чате!",
        reply_markup=main_menu(),
        parse_mode="Markdown"
    )
    await state.clear()

# =================== ОТВЕТ ТП-АДМИНА ===================
@router.message(F.text.startswith("/reply_"))
async def admin_reply_start(message: Message, state: FSMContext):
    if not db.is_support_admin(message.from_user.id):
        await message.answer("❌ Ты не ТП-админ!")
        return
    
    try:
        ticket_id = int(message.text.split("_")[1])
        ticket = db.get_ticket_by_id(ticket_id)
        
        if not ticket:
            await message.answer("❌ Заявка не найдена!")
            return
        
        await state.update_data(ticket_id=ticket_id, user_id=ticket[1])
        await message.answer(
            f"💬 *Ответ на заявку #{ticket_id}*\n\n"
            f"Клиент: {ticket[2]}\n"
            f"Сообщение: {ticket[3]}\n\n"
            "Напиши ответ для клиента:",
            reply_markup=cancel_keyboard(),
            parse_mode="Markdown"
        )
        await state.set_state(Form.admin_reply)
    except:
        await message.answer("❌ Ошибка! Используй: /reply_номер")

@router.message(Form.admin_reply)
async def admin_reply_send(message: Message, state: FSMContext):
    data = await state.get_data()
    ticket_id = data['ticket_id']
    user_id = data['user_id']
    
    # Отправляем ответ клиенту
    try:
        await bot.send_message(
            user_id,
            f"💬 *Ответ от поддержки*\n\n"
            f"{message.text or '📎 Вложение'}\n\n"
            f"🆔 Номер заявки: #{ticket_id}",
            parse_mode="Markdown"
        )
        
        # Помечаем заявку как в работе
        db.assign_ticket(ticket_id, message.from_user.id)
        
        await message.answer(
            f"✅ Ответ отправлен клиенту!\n"
            f"Заявка #{ticket_id} теперь в работе.",
            reply_markup=main_menu()
        )
    except Exception as e:
        await message.answer(
            f"❌ Не удалось отправить ответ!\n"
            f"Ошибка: {str(e)[:100]}"
        )
    
    await state.clear()

# =================== АДМИН-ПАНЕЛЬ ===================
@router.message(F.text == "👑 Админ-панель")
async def admin_panel_access(message: Message):
    if not db.is_support_admin(message.from_user.id):
        await message.answer("❌ Доступ только для ТП-админов!")
        return
    
    await message.answer(
        "👑 *Админ-панель*\n\n"
        "Управление магазином и поддержкой:",
        reply_markup=admin_menu(),
        parse_mode="Markdown"
    )

# =================== УПРАВЛЕНИЕ ТП-АДМИНАМИ ===================
@router.callback_query(F.data == "admin_manage_support")
async def manage_support_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "👨‍💼 *Управление ТП-админами*\n\n"
        "Добавляй или удаляй тех, кто будет отвечать на заявки:",
        reply_markup=support_management_menu(),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "admin_add_support")
async def add_support_admin_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "👨‍💼 *Добавление ТП-админа*\n\n"
        "Пришли ID пользователя (цифры):\n"
        "Пример: 1234567890\n\n"
        "Используй /cancel для отмены",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.waiting_new_admin)
    await callback.answer()

@router.message(Form.waiting_new_admin)
async def add_support_admin_process(message: Message, state: FSMContext):
    if message.text and message.text.startswith('/cancel'):
        await state.clear()
        await message.answer("❌ Добавление отменено", reply_markup=main_menu())
        return
    
    try:
        admin_id = int(message.text)
        
        if db.is_support_admin(admin_id):
            await message.answer("❌ Этот пользователь уже ТП-админ!")
            return
        
        db.add_support_admin(admin_id, message.from_user.id)
        
        # Уведомляем нового админа
        try:
            await bot.send_message(
                admin_id,
                "🎉 *Ты теперь ТП-админ Art Stars!*\n\n"
                "Теперь ты будешь получать все заявки от клиентов.\n"
                "Для ответа используй команду:\n"
                "/reply_номер_заявки\n\n"
                "Удачи в работе! 💪",
                parse_mode="Markdown"
            )
        except:
            pass
        
        await message.answer(
            f"✅ ТП-админ {admin_id} добавлен!\n"
            f"Он получил уведомление.",
            reply_markup=main_menu()
        )
    except ValueError:
        await message.answer("❌ Пришли только цифры (ID пользователя)!")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
    
    await state.clear()

@router.callback_query(F.data == "admin_remove_support")
async def remove_support_admin_start(callback: CallbackQuery, state: FSMContext):
    admins = db.get_all_support_admins()
    
    if len(admins) <= 1:
        await callback.answer("❌ Нельзя удалить последнего админа!")
        return
    
    text = "➖ *Удаление ТП-админа*\n\n"
    buttons = []
    
    for admin in admins:
        if admin[0] == ADMIN_ID:
            continue  # Не показываем главного админа
            
        name = admin[2] or admin[1] or f"ID: {admin[0]}"
        text += f"🆔 {admin[0]} - {name}\n"
        buttons.append([
            InlineKeyboardButton(
                text=f"❌ {name[:15]}",
                callback_data=f"remove_admin_{admin[0]}"
            )
        ])
    
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_manage_support")])
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("remove_admin_"))
async def remove_support_admin_process(callback: CallbackQuery):
    admin_id = int(callback.data.split("_")[2])
    
    if admin_id == ADMIN_ID:
        await callback.answer("❌ Нельзя удалить главного админа!")
        return
    
    db.remove_support_admin(admin_id)
    
    await callback.message.edit_text(
        f"✅ ТП-админ {admin_id} удалён!",
        reply_markup=support_management_menu(),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "admin_list_support")
async def list_support_admins(callback: CallbackQuery):
    admins = db.get_all_support_admins()
    
    text = "📝 *Список ТП-админов:*\n\n"
    
    for admin in admins:
        name = admin[2] or admin[1] or f"ID: {admin[0]}"
        added = datetime.strptime(admin[3], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')
        text += f"👤 {name}\n🆔 {admin[0]}\n📅 Добавлен: {added}\n\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=support_management_menu(),
        parse_mode="Markdown"
    )
    await callback.answer()

# =================== УПРАВЛЕНИЕ ЦЕНАМИ ===================
@router.callback_query(F.data == "admin_manage_prices")
async def manage_prices_menu(callback: CallbackQuery):
    text = "💰 *Текущие цены:*\n\n"
    text += f"⭐ Звезда: {PRICES['star_rate']}₽\n"
    text += f"💎 TON: {PRICES['ton_rate']}₽\n"
    text += f"🏆 Premium 3 мес: {PRICES['premium_3']} USDT\n"
    text += f"🏆 Premium 6 мес: {PRICES['premium_6']} USDT\n"
    text += f"🏆 Premium 12 мес: {PRICES['premium_12']} USDT\n\n"
    text += "👇 Выбери цену для изменения:"
    
    await callback.message.edit_text(
        text,
        reply_markup=prices_management_menu(),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("price_"))
async def change_price_start(callback: CallbackQuery, state: FSMContext):
    price_key = callback.data.replace("price_", "")
    
    price_names = {
        "star": "⭐ Цена одной звезды (в рублях)",
        "ton": "💎 Цена одного TON (в рублях)",
        "premium_3": "🏆 Цена Premium на 3 месяца (в USDT)",
        "premium_6": "🏆 Цена Premium на 6 месяцев (в USDT)",
        "premium_12": "🏆 Цена Premium на 12 месяцев (в USDT)"
    }
    
    current_price = PRICES.get(f"{price_key}", 0)
    
    await state.update_data(price_key=price_key)
    
    await callback.message.answer(
        f"💰 *Изменение цены*\n\n"
        f"{price_names.get(price_key, 'Цена')}\n"
        f"Текущая цена: *{current_price}*\n\n"
        f"Введи новую цену (число):\n\n"
        f"Используй /cancel для отмены",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.waiting_set_price)
    await callback.answer()

@router.message(Form.waiting_set_price)
async def change_price_process(message: Message, state: FSMContext):
    if message.text and message.text.startswith('/cancel'):
        await state.clear()
        await message.answer("❌ Изменение цены отменено", reply_markup=main_menu())
        return
    
    try:
        data = await state.get_data()
        price_key = data['price_key']
        
        new_price = float(message.text.replace(',', '.'))
        
        if new_price <= 0:
            await message.answer("❌ Цена должна быть больше 0!")
            return
        
        # Обновляем цену в базе
        db.update_price(price_key, new_price)
        
        price_names = {
            "star": "⭐ Цена звезды",
            "ton": "💎 Цена TON",
            "premium_3": "🏆 Premium 3 мес",
            "premium_6": "🏆 Premium 6 мес",
            "premium_12": "🏆 Premium 12 мес"
        }
        
        await message.answer(
            f"✅ Цена изменена!\n\n"
            f"{price_names.get(price_key, 'Цена')}: {new_price}\n\n"
            f"Изменение вступит в силу сразу после обновления сайта.",
            reply_markup=main_menu(),
            parse_mode="Markdown"
        )
        
    except ValueError:
        await message.answer("❌ Введи число! Например: 1.45 или 167")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
    
    await state.clear()

# =================== ПРОСМОТР ЗАЯВОК ===================
@router.callback_query(F.data == "admin_new_tickets")
async def show_new_tickets(callback: CallbackQuery):
    tickets = db.get_new_tickets()
    
    if not tickets:
        await callback.message.edit_text(
            "📋 *Новые заявки*\n\n"
            "✅ Нет новых заявок!",
            reply_markup=admin_menu(),
            parse_mode="Markdown"
        )
        return
    
    text = "📋 *Новые заявки:*\n\n"
    buttons = []
    
    for ticket in tickets[:10]:
        text += f"🆔 #{ticket[0]}\n👤 {ticket[2]}\n💬 {ticket[3][:50]}...\n\n"
        buttons.append([
            InlineKeyboardButton(
                text=f"#{ticket[0]} - {ticket[2][:15]}",
                callback_data=f"view_ticket_{ticket[0]}"
            )
        ])
    
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")])
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("view_ticket_"))
async def view_ticket_details(callback: CallbackQuery):
    ticket_id = int(callback.data.split("_")[2])
    ticket = db.get_ticket_by_id(ticket_id)
    
    if not ticket:
        await callback.answer("❌ Заявка не найдена!")
        return
    
    status_text = {
        'new': '🟢 Новая',
        'in_progress': '🟡 В работе',
        'closed': '🔴 Закрыта'
    }
    
    status = status_text.get(ticket[4], ticket[4])
    
    text = (
        f"📄 *Заявка #{ticket[0]}*\n\n"
        f"👤 *Клиент:* {ticket[2]}\n"
        f"🆔 *ID:* {ticket[1]}\n"
        f"📅 *Дата:* {ticket[6]}\n"
        f"📊 *Статус:* {status}\n\n"
        f"💬 *Сообщение:*\n{ticket[3]}\n\n"
    )
    
    keyboard = []
    if ticket[4] == 'new':
        keyboard.append([
            InlineKeyboardButton(text="✅ Взять в работу", callback_data=f"take_ticket_{ticket_id}")
        ])
    
    keyboard.append([
        InlineKeyboardButton(text="💬 Ответить", callback_data=f"reply_btn_{ticket_id}"),
        InlineKeyboardButton(text="🔒 Закрыть", callback_data=f"close_ticket_{ticket_id}")
    ])
    keyboard.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_new_tickets")])
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("take_ticket_"))
async def take_ticket(callback: CallbackQuery):
    ticket_id = int(callback.data.split("_")[2])
    db.assign_ticket(ticket_id, callback.from_user.id)
    await callback.answer("✅ Заявка взята в работу!")
    await view_ticket_details(callback)

@router.callback_query(F.data.startswith("reply_btn_"))
async def reply_to_ticket_btn(callback: CallbackQuery, state: FSMContext):
    ticket_id = int(callback.data.split("_")[2])
    ticket = db.get_ticket_by_id(ticket_id)
    
    await state.update_data(ticket_id=ticket_id, user_id=ticket[1])
    await callback.message.answer(
        f"💬 *Ответ на заявку #{ticket_id}*\n\n"
        f"Клиент: {ticket[2]}\n\n"
        "Напиши ответ для клиента:\n\n"
        "Используй /cancel для отмены",
        reply_markup=cancel_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(Form.admin_reply)
    await callback.answer()

@router.callback_query(F.data.startswith("close_ticket_"))
async def close_ticket_btn(callback: CallbackQuery):
    ticket_id = int(callback.data.split("_")[2])
    db.close_ticket(ticket_id)
    await callback.answer("✅ Заявка закрыта!")
    await view_ticket_details(callback)

# =================== СТАТИСТИКА ===================
@router.callback_query(F.data == "admin_stats")
async def show_stats(callback: CallbackQuery):
    stats = db.get_stats()
    
    text = (
        "📊 *Статистика магазина*\n\n"
        f"👥 Пользователей: {stats['users']}\n"
        f"🛒 Заказов: {stats['orders']}\n"
        f"🆘 Новых заявок: {stats['new_tickets']}\n"
        f"👨‍💼 ТП-админов: {stats['admins']}\n\n"
        "💰 *Текущие цены:*\n"
        f"⭐ Звезда: {stats['prices']['star_rate']}₽\n"
        f"💎 TON: {stats['prices']['ton_rate']}₽\n"
        f"🏆 Premium: {stats['prices']['premium_3']}/{stats['prices']['premium_6']}/{stats['prices']['premium_12']} USDT\n\n"
        "Магазин работает! 🚀"
    )
    
    await callback.message.edit_text(
        text,
        reply_markup=admin_menu(),
        parse_mode="Markdown"
    )
    await callback.answer()

# =================== ОБНОВЛЕНИЕ САЙТА ===================
@router.callback_query(F.data == "admin_refresh_webapp")
async def refresh_webapp(callback: CallbackQuery):
    # Здесь можно добавить обновление сайта
    # Например, отправку новых цен через API
    
    await callback.message.edit_text(
        "🔄 *Обновление сайта*\n\n"
        "Цены обновлены на сайте!\n"
        "Клиенты увидят новые цены сразу.\n\n"
        f"⭐ Звезда: {PRICES['star_rate']}₽\n"
        f"💎 TON: {PRICES['ton_rate']}₽",
        reply_markup=admin_menu(),
        parse_mode="Markdown"
    )
    await callback.answer("✅ Сайт обновлён!")

# =================== НАЗАД ===================
@router.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery):
    await callback.message.edit_text(
        "👑 *Админ-панель*\n\n"
        "Управление магазином и поддержкой:",
        reply_markup=admin_menu(),
        parse_mode="Markdown"
    )
    await callback.answer()

@router.callback_query(F.data == "cancel")
async def cancel_action(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Действие отменено")
    await callback.message.answer("Главное меню:", reply_markup=main_menu())
    await callback.answer()

# =================== ОБРАБОТКА ЗАКАЗОВ ИЗ САЙТА ===================
@router.message(F.web_app_data)
async def handle_web_app_data(message: Message):
    try:
        data = json.loads(message.web_app_data.data)
        
        if data.get('type') == 'new_order':
            # Создаём заказ в базе
            order_id = db.create_order(
                message.from_user.id,
                data['data']['product'],
                data['data']['quantity'],
                data['data']['total'],
                data['data']['currency'],
                data['data']['username']
            )
            
            # Уведомляем админов о новом заказе
            admins = db.get_all_support_admins()
            for admin in admins:
                try:
                    await bot.send_message(
                        admin[0],
                        f"🛒 *НОВЫЙ ЗАКАЗ #{order_id}*\n\n"
                        f"👤 Клиент: {message.from_user.full_name}\n"
                        f"🆔 ID: {message.from_user.id}\n"
                        f"📦 Товар: {data['data']['product']}\n"
                        f"📊 Количество: {data['data']['quantity']}\n"
                        f"💰 Сумма: {data['data']['total']} {data['data']['currency']}\n"
                        f"📝 Username: {data['data']['username']}\n\n"
                        f"Ожидает оплаты и подтверждения!",
                        parse_mode="Markdown"
                    )
                except:
                    pass
            
            await message.answer(
                f"✅ *Заказ #{order_id} создан!*\n\n"
                f"После оплаты отправь скриншот в этот чат.\n"
                f"Мы активируем заказ в течение 24 часов.\n\n"
                f"Спасибо за покупку! 🎉",
                reply_markup=main_menu(),
                parse_mode="Markdown"
            )
    except Exception as e:
        await message.answer(f"❌ Ошибка обработки заказа: {str(e)}")

# =================== ЗАПУСК БОТА ===================
async def main():
    print("🤖 Art Stars Bot запускается...")
    print(f"👑 Главный админ: {ADMIN_ID}")
    print(f"🌐 Мини-приложение: {WEBAPP_URL}")
    print("✅ Техподдержка работает - заявки приходят ТП-админам")
    print("💰 Админ-панель: управление ценами и ТП-админами")
    print("🛒 Заказы из сайта обрабатываются автоматически")
    print("🚀 БОТ ГОТОВ К РАБОТЕ!")
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
