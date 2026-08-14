# YuuY Chat API Documentation

## Bot API (Отдельный сервер на порту 5001)

### Запуск Bot API сервера:
```bash
cd /workspace/bot_api
python bot_server.py
```

### endpoints:

#### 1. Создание бота
**POST** `/api/bot/create`
```json
{
    "owner_id": 1,
    "username": "mybot",
    "display_name": "My Bot"
}
```

#### 2. Информация о боте
**GET** `/api/bot/me`
Header: `X-Bot-Token: your_token`

#### 3. Отправка сообщения
**POST** `/api/bot/send`
```json
{
    "user_id": 5,
    "content": "Hello!",
    "chat_type": "private"
}
```

#### 4. Получение сообщений
**GET** `/api/bot/messages?since_id=0&limit=50`
Header: `X-Bot-Token: your_token`

---

## Основной сервер API (порт 5000)

### Bot endpoints в основном сервере:

#### Создать бота
**POST** `/api/bots/create`
```json
{
    "username": "@mybot",
    "display_name": "My Bot"
}
```

#### Мои боты
**GET** `/api/my_bots`

#### Обновить бота
**POST** `/api/bot/update`
```json
{
    "bot_id": 1,
    "display_name": "New Name",
    "webhook_url": "https://..."
}
```

#### Удалить бота
**POST** `/api/bot/delete`
```json
{"bot_id": 1}
```

---

## GUI Изменения

### Telegram-стиль интерфейс:
1. **Кнопка "+" слева** - в секции друзей для создания нового чата
2. **Друзья в ЛС слева** - список чатов отображается в sidebar как в Telegram
3. **Поиск пользователей** - с фильтром по имени
4. **Боты помечены** - badge "BOT" рядом с именем бота
5. **Мобильная адаптация** - responsive дизайн для телефонов

### Создание ботов через UI:
1. Нажмите "+" в секции "Friends & Chats"
2. Выберите "+ Create Bot"
3. Введите @username и display name
4. Получите API токен

---

## Специальный пользователь @botcreatr

Пользователь с тегом @botcreatr может создавать неограниченное количество ботов и кастомизировать их через API.
