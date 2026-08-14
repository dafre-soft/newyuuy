"""
Bot API для YuuY Chat - отдельный сервер ботов
Запускается на порту 5001
"""

import os
import json
import sqlite3
import hashlib
import secrets
from datetime import datetime
from flask import Flask, request, jsonify, session
from functools import wraps

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
DB_PATH = '../chat_database.db'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# Таблица для хранения созданных ботов
def init_bot_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS bots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER NOT NULL,
        username TEXT UNIQUE NOT NULL,
        display_name TEXT,
        bio TEXT DEFAULT '',
        avatar_url TEXT DEFAULT '/static/default_avatar.png',
        api_token TEXT UNIQUE NOT NULL,
        webhook_url TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        commands TEXT DEFAULT '{}',
        auto_responses TEXT DEFAULT '{}'
    )''')
    
    # Таблица сообщений для ботов
    c.execute('''CREATE TABLE IF NOT EXISTS bot_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        content TEXT,
        timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
        is_from_bot INTEGER DEFAULT 0
    )''')
    
    conn.commit()
    conn.close()

init_bot_db()

# Проверка токена бота
def bot_auth_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('X-Bot-Token') or request.args.get('token')
        if not token:
            return jsonify({"error": "Missing bot token"}), 401
        
        conn = get_db()
        bot = conn.execute('SELECT * FROM bots WHERE api_token=?', (token,)).fetchone()
        conn.close()
        
        if not bot or not bot['is_active']:
            return jsonify({"error": "Invalid or inactive bot token"}), 403
        
        request.bot = dict(bot)
        return f(*args, **kwargs)
    return decorated_function

# Создание бота
@app.route('/api/bot/create', methods=['POST'])
def create_bot():
    data = request.json
    owner_id = data.get('owner_id')
    username = data.get('username', '').strip().lower()
    display_name = data.get('display_name', username)
    
    if not username or len(username) < 3:
        return jsonify({"error": "Invalid username"}), 400
    
    if not username.startswith('@'):
        username = '@' + username
    
    conn = get_db()
    
    # Проверка существования
    existing = conn.execute('SELECT 1 FROM bots WHERE username=?', (username,)).fetchone()
    if existing:
        conn.close()
        return jsonify({"error": "Bot username already taken"}), 400
    
    # Генерация токена
    api_token = 'bot_' + secrets.token_urlsafe(32)
    
    try:
        conn.execute('''INSERT INTO bots 
                       (owner_id, username, display_name, api_token) 
                       VALUES (?, ?, ?, ?)''',
                    (owner_id, username, display_name, api_token))
        conn.commit()
        
        bot = conn.execute('SELECT * FROM bots WHERE username=?', (username,)).fetchone()
        conn.close()
        
        return jsonify({
            "success": True,
            "bot": {
                "id": bot['id'],
                "username": bot['username'],
                "display_name": bot['display_name'],
                "api_token": bot['api_token']
            },
            "message": f"Bot {username} created successfully!"
        })
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "Failed to create bot"}), 500

# Получение информации о боте
@app.route('/api/bot/me', methods=['GET'])
@bot_auth_required
def get_bot_info():
    return jsonify({
        "id": request.bot['id'],
        "username": request.bot['username'],
        "display_name": request.bot['display_name'],
        "bio": request.bot['bio'],
        "avatar_url": request.bot['avatar_url'],
        "webhook_url": request.bot['webhook_url'],
        "is_active": bool(request.bot['is_active']),
        "commands": json.loads(request.bot['commands'] or '{}'),
        "auto_responses": json.loads(request.bot['auto_responses'] or '{}')
    })

# Обновление информации о боте
@app.route('/api/bot/update', methods=['POST'])
@bot_auth_required
def update_bot():
    data = request.json
    conn = get_db()
    updates = []
    params = []
    
    if 'display_name' in data:
        updates.append('display_name=?')
        params.append(data['display_name'][:50])
    if 'bio' in data:
        updates.append('bio=?')
        params.append(data['bio'][:500])
    if 'webhook_url' in data:
        updates.append('webhook_url=?')
        params.append(data['webhook_url'][:500])
    if 'commands' in data:
        updates.append('commands=?')
        params.append(json.dumps(data['commands']))
    if 'auto_responses' in data:
        updates.append('auto_responses=?')
        params.append(json.dumps(data['auto_responses']))
    
    if updates:
        params.append(request.bot['id'])
        conn.execute(f"UPDATE bots SET {', '.join(updates)} WHERE id=?", params)
        conn.commit()
    
    conn.close()
    return jsonify({"success": True})

# Отправка сообщения от имени бота
@app.route('/api/bot/send', methods=['POST'])
@bot_auth_required
def bot_send_message():
    data = request.json
    user_id = data.get('user_id')
    content = data.get('content', '')
    chat_type = data.get('chat_type', 'private')
    target_id = data.get('target_id')
    
    if not user_id and not target_id:
        return jsonify({"error": "user_id or target_id required"}), 400
    
    conn = get_db()
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Сохраняем сообщение в базе
    conn.execute('''INSERT INTO messages 
                   (sender_id, chat_type, target_id, type, content, timestamp, read_by)
                   VALUES (?, ?, ?, 'text', ?, ?, '[]')''',
                (request.bot['id'], chat_type, target_id or user_id, content, timestamp))
    
    # Логируем для бота
    conn.execute('''INSERT INTO bot_messages 
                   (bot_id, user_id, content, is_from_bot)
                   VALUES (?, ?, ?, 1)''',
                (request.bot['id'], user_id or target_id, content))
    
    conn.commit()
    msg_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
    conn.close()
    
    return jsonify({
        "success": True,
        "message_id": msg_id,
        "timestamp": timestamp
    })

# Получение сообщений для бота (webhook polling)
@app.route('/api/bot/messages', methods=['GET'])
@bot_auth_required
def get_bot_messages():
    since_id = request.args.get('since_id', 0, type=int)
    limit = request.args.get('limit', 50, type=int)
    
    conn = get_db()
    messages = conn.execute('''
        SELECT m.*, u.username as user_username, u.display_name as user_display_name
        FROM messages m
        JOIN users u ON u.id = m.sender_id
        WHERE m.target_id = ? AND m.sender_id != ? AND m.id > ?
        ORDER BY m.id ASC
        LIMIT ?
    ''', (request.bot['id'], request.bot['id'], since_id, limit)).fetchall()
    
    conn.close()
    
    return jsonify([{
        "id": msg['id'],
        "from_user": {
            "id": msg['sender_id'],
            "username": msg['user_username'],
            "display_name": msg['user_display_name']
        },
        "content": msg['content'],
        "timestamp": msg['timestamp'],
        "chat_type": msg['chat_type']
    } for msg in messages])

# Удаление бота
@app.route('/api/bot/delete', methods=['POST'])
@bot_auth_required
def delete_bot():
    conn = get_db()
    conn.execute('UPDATE bots SET is_active=0 WHERE id=?', (request.bot['id'],))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Bot deactivated"})

# Список всех ботов пользователя
@app.route('/api/bots/list/<int:owner_id>', methods=['GET'])
def list_bots(owner_id):
    conn = get_db()
    bots = conn.execute('''
        SELECT id, username, display_name, api_token, is_active, created_at
        FROM bots WHERE owner_id=?
    ''', (owner_id,)).fetchall()
    conn.close()
    
    return jsonify([{
        "id": bot['id'],
        "username": bot['username'],
        "display_name": bot['display_name'],
        "api_token": bot['api_token'][:20] + '...' if bot['api_token'] else None,
        "is_active": bool(bot['is_active']),
        "created_at": bot['created_at']
    } for bot in bots])

if __name__ == '__main__':
    print("🤖 Bot API Server starting on port 5001...")
    app.run(host='0.0.0.0', port=5001, debug=True)
