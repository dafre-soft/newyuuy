# YuuY Chat Bot API Documentation

## Overview

The YuuY Chat Bot API allows developers to create custom bots that can interact with users in the chat system. Bots can send messages, respond to commands, and automate various tasks.

## Base URL

```
http://localhost:5001
```

The Bot API runs on a separate server (port 5001) from the main chat application (port 5000).

## Authentication

All bot API endpoints require authentication using a bot token. The token must be included in the request header:

```
X-Bot-Token: your_bot_token_here
```

## Creating a Bot

### Special Bot Creator User: @botcreatr

The user `@botcreatr` is the dedicated bot creator account. Users can interact with this bot to create and customize their own bots.

### API Endpoint: Create Bot

**POST** `/api/bot/create`

Creates a new bot for the specified owner.

**Request Body:**
```json
{
    "owner_id": 1,
    "username": "@mybot",
    "display_name": "My Awesome Bot",
    "bio": "A helpful assistant bot",
    "avatar_url": "/static/default_avatar.png"
}
```

**Response:**
```json
{
    "success": true,
    "bot": {
        "id": 5,
        "username": "@mybot",
        "display_name": "My Awesome Bot",
        "api_token": "bot_xxxxxxxxxxxxxxxxxxxxx"
    },
    "message": "Bot @mybot created successfully!"
}
```

## Bot API Endpoints

### Get Bot Information

**GET** `/api/bot/me`

Retrieves information about the authenticated bot.

**Headers:**
```
X-Bot-Token: your_bot_token
```

**Response:**
```json
{
    "id": 5,
    "username": "@mybot",
    "display_name": "My Awesome Bot",
    "bio": "A helpful assistant bot",
    "avatar_url": "/static/default_avatar.png",
    "webhook_url": null,
    "is_active": true,
    "commands": {},
    "auto_responses": {}
}
```

### Update Bot Information

**POST** `/api/bot/update`

Updates bot configuration.

**Headers:**
```
X-Bot-Token: your_bot_token
```

**Request Body:**
```json
{
    "display_name": "Updated Bot Name",
    "bio": "Updated bio",
    "webhook_url": "https://example.com/webhook",
    "commands": {
        "/start": "Welcome message",
        "/help": "Help information"
    },
    "auto_responses": {
        "hello": "Hi there!",
        "how are you": "I'm doing great!"
    }
}
```

**Response:**
```json
{
    "success": true
}
```

### Send Message as Bot

**POST** `/api/bot/send`

Sends a message from the bot to a user.

**Headers:**
```
X-Bot-Token: your_bot_token
```

**Request Body:**
```json
{
    "user_id": 5,
    "content": "Hello! I'm a bot.",
    "chat_type": "private",
    "target_id": null
}
```

**Response:**
```json
{
    "success": true,
    "message_id": 123,
    "timestamp": "2024-01-15 10:30:00"
}
```

### Get Messages for Bot

**GET** `/api/bot/messages`

Retrieves messages sent to the bot (for polling-based bots).

**Headers:**
```
X-Bot-Token: your_bot_token
```

**Query Parameters:**
- `since_id` (optional): Only return messages after this ID
- `limit` (optional): Maximum number of messages to return (default: 50)

**Response:**
```json
[
    {
        "id": 100,
        "from_user": {
            "id": 5,
            "username": "john_doe",
            "display_name": "John Doe"
        },
        "content": "Hello bot!",
        "timestamp": "2024-01-15 10:29:00",
        "chat_type": "private"
    }
]
```

### List User's Bots

**GET** `/api/bots/list/<owner_id>`

Lists all bots owned by a specific user.

**Response:**
```json
[
    {
        "id": 5,
        "username": "@mybot",
        "display_name": "My Awesome Bot",
        "api_token": "bot_xxxxx...",
        "is_active": true,
        "created_at": "2024-01-15 10:00:00"
    }
]
```

### Delete/Deactivate Bot

**POST** `/api/bot/delete`

Deactivates a bot (soft delete).

**Headers:**
```
X-Bot-Token: your_bot_token
```

**Response:**
```json
{
    "success": true,
    "message": "Bot deactivated"
}
```

## Error Responses

All endpoints may return error responses in the following format:

```json
{
    "error": "Error message description"
}
```

**Common HTTP Status Codes:**
- `200`: Success
- `400`: Bad Request (invalid parameters)
- `401`: Unauthorized (missing or invalid token)
- `403`: Forbidden (inactive bot)
- `404`: Not Found
- `500`: Internal Server Error

## Example: Python Bot Client

```python
import requests

BOT_TOKEN = "bot_your_token_here"
BASE_URL = "http://localhost:5001"

headers = {"X-Bot-Token": BOT_TOKEN}

# Get bot info
response = requests.get(f"{BASE_URL}/api/bot/me", headers=headers)
print(response.json())

# Send a message
response = requests.post(
    f"{BASE_URL}/api/bot/send",
    headers=headers,
    json={
        "user_id": 5,
        "content": "Hello from Python!"
    }
)
print(response.json())

# Poll for messages
response = requests.get(
    f"{BASE_URL}/api/bot/messages?since_id=0&limit=10",
    headers=headers
)
messages = response.json()
for msg in messages:
    print(f"From {msg['from_user']['username']}: {msg['content']}")
```

## Example: Node.js Bot Client

```javascript
const axios = require('axios');

const BOT_TOKEN = 'bot_your_token_here';
const BASE_URL = 'http://localhost:5001';

const api = axios.create({
    baseURL: BASE_URL,
    headers: {'X-Bot-Token': BOT_TOKEN}
});

// Get bot info
async function getBotInfo() {
    const response = await api.get('/api/bot/me');
    console.log(response.data);
}

// Send a message
async function sendMessage(userId, content) {
    const response = await api.post('/api/bot/send', {
        user_id: userId,
        content: content
    });
    console.log(response.data);
}

// Poll for messages
async function pollMessages(sinceId = 0) {
    const response = await api.get('/api/bot/messages', {
        params: {since_id: sinceId, limit: 10}
    });
    return response.data;
}
```

## Webhook Support

Bots can optionally configure a webhook URL to receive real-time notifications when new messages arrive. Set the `webhook_url` in the bot update endpoint.

## Rate Limiting

To prevent abuse, the Bot API implements rate limiting:
- Maximum 30 requests per minute per bot
- Maximum 100 messages sent per hour per bot

Exceeding these limits will result in a `429 Too Many Requests` response.

## Best Practices

1. **Secure Your Token**: Never share your bot token publicly
2. **Poll Responsibly**: Use `since_id` to only fetch new messages
3. **Handle Errors**: Always check for error responses
4. **Respect Rate Limits**: Implement exponential backoff for retries
5. **User Experience**: Provide clear commands and help text

## Support

For questions or issues, contact the server administrator or open an issue in the project repository.
