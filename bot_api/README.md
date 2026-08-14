# Bot API Documentation

## Overview
Bot API для YuuY Chat - отдельный сервер для создания и управления ботами.

## Запуск
```bash
python bot_server.py
```
Сервер запускается на порту **5001**

---

## Authentication
Все запросы к API бота требуют заголовок:
```
X-Bot-Token: your_bot_token
```
Или параметр в URL:
```
?token=your_bot_token
```

---

## Endpoints

### 1. Создание бота
**POST** `/api/bot/create`

Создаёт нового бота и возвращает API токен.

**Request Body:**
```json
{
    "owner_id": 1,
    "username": "mybot",
    "display_name": "My Awesome Bot"
}
```

**Response:**
```json
{
    "success": true,
    "bot": {
        "id": 1,
        "username": "@mybot",
        "display_name": "My Awesome Bot",
        "api_token": "bot_abc123xyz..."
    },
    "message": "Bot @mybot created successfully!"
}
```

---

### 2. Информация о боте
**GET** `/api/bot/me`

Получение информации о текущем боте.

**Headers:**
```
X-Bot-Token: your_bot_token
```

**Response:**
```json
{
    "id": 1,
    "username": "@mybot",
    "display_name": "My Awesome Bot",
    "bio": "I am a helpful bot",
    "avatar_url": "/static/default_avatar.png",
    "webhook_url": null,
    "is_active": true,
    "commands": {},
    "auto_responses": {}
}
```

---

### 3. Обновление бота
**POST** `/api/bot/update`

Обновляет информацию о боте.

**Request Body:**
```json
{
    "display_name": "New Bot Name",
    "bio": "Updated bio",
    "webhook_url": "https://example.com/webhook",
    "commands": {
        "/start": "Hello!",
        "/help": "Available commands..."
    },
    "auto_responses": {
        "привет": "Здравствуйте!",
        "как дела": "Отлично, спасибо!"
    }
}
```

**Response:**
```json
{
    "success": true
}
```

---

### 4. Отправка сообщения
**POST** `/api/bot/send`

Отправляет сообщение от имени бота.

**Request Body:**
```json
{
    "user_id": 5,
    "content": "Hello from bot!",
    "chat_type": "private",
    "target_id": null
}
```

**Response:**
```json
{
    "success": true,
    "message_id": 123,
    "timestamp": "2024-01-15 14:30:00"
}
```

---

### 5. Получение сообщений
**GET** `/api/bot/messages`

Получает новые сообщения для бота (polling).

**Query Parameters:**
- `since_id` (int): ID последнего полученного сообщения
- `limit` (int): Максимальное количество сообщений (по умолчанию 50)

**Response:**
```json
[
    {
        "id": 124,
        "from_user": {
            "id": 5,
            "username": "john",
            "display_name": "John Doe"
        },
        "content": "Hello bot!",
        "timestamp": "2024-01-15 14:31:00",
        "chat_type": "private"
    }
]
```

---

### 6. Список ботов пользователя
**GET** `/api/bots/list/<owner_id>`

Получение всех ботов, созданных пользователем.

**Response:**
```json
[
    {
        "id": 1,
        "username": "@mybot",
        "display_name": "My Awesome Bot",
        "api_token": "bot_abc123...",
        "is_active": true,
        "created_at": "2024-01-15 10:00:00"
    }
]
```

---

### 7. Удаление бота
**POST** `/api/bot/delete`

Деактивирует бота (мягкое удаление).

**Response:**
```json
{
    "success": true,
    "message": "Bot deactivated"
}
```

---

## Пример использования на Python

```python
import requests

BOT_TOKEN = "bot_your_token_here"
BASE_URL = "http://localhost:5001"

headers = {"X-Bot-Token": BOT_TOKEN}

# Получить информацию о боте
response = requests.get(f"{BASE_URL}/api/bot/me", headers=headers)
print(response.json())

# Отправить сообщение
response = requests.post(f"{BASE_URL}/api/bot/send", 
    headers=headers,
    json={"user_id": 5, "content": "Hello!"})
print(response.json())

# Получить новые сообщения
response = requests.get(f"{BASE_URL}/api/bot/messages?since_id=0", 
    headers=headers)
messages = response.json()
for msg in messages:
    print(f"From {msg['from_user']['username']}: {msg['content']}")
```

---

## Пример использования на JavaScript

```javascript
const BOT_TOKEN = "bot_your_token_here";
const BASE_URL = "http://localhost:5001";

const headers = {"X-Bot-Token": BOT_TOKEN};

// Получить информацию о боте
async function getBotInfo() {
    const response = await fetch(`${BASE_URL}/api/bot/me`, {headers});
    return await response.json();
}

// Отправить сообщение
async function sendMessage(userId, content) {
    const response = await fetch(`${BASE_URL}/api/bot/send`, {
        method: 'POST',
        headers: {...headers, 'Content-Type': 'application/json'},
        body: JSON.stringify({user_id: userId, content})
    });
    return await response.json();
}

// Получить сообщения
async function getMessages(sinceId = 0) {
    const response = await fetch(`${BASE_URL}/api/bot/messages?since_id=${sinceId}`, {headers});
    return await response.json();
}
```

---

## Special User: @botcreatr

Пользователь с тегом **@botcreatr** является специальным создателем ботов.
Этот пользователь может:
- Создавать неограниченное количество ботов
- Кастомизировать всех созданных ботов
- Получать API ссылки для управления ботами

Для создания бота через интерфейс:
1. Найдите пользователя @botcreatr
2. Откройте профиль
3. Используйте кнопку "Create Bot"
4. Настройте бота и получите API токен
