# YuuY Chat - Telegram-Style GUI Implementation

## Overview

This document describes the Telegram-style GUI implementation for YuuY Chat, featuring:
- Left sidebar with friends list (like Telegram)
- Mobile-responsive design
- User tagging (@mentions)
- Bot creation via @botcreatr
- Modern chat interface

## File Structure

```
/workspace/
├── server.py                 # Main Flask server with API endpoints
├── bot_api/
│   └── bot_server.py        # Separate Bot API server (port 5001)
├── templates/
│   └── main.html            # Main chat interface HTML
├── static/
│   ├── css/
│   │   └── main.css         # Styles with Telegram-like design
│   └── js/
│       └── main.js          # Frontend JavaScript
├── BOT_API_DOCUMENTATION.md # Complete Bot API documentation
└── README_TELEGRAM_GUI.md   # This file
```

## Key Features

### 1. Left Sidebar (Telegram-Style)

The sidebar is positioned on the left and contains:
- **Profile Header**: User avatar, name, and role
- **Navigation Tabs**: Chats, Groups, Feed, Pages
- **Search Bar**: Filter chats and contacts
- **Friends Section**: List of accepted friends with online status
- **Recent Chats**: Recently active conversations
- **+ Button**: Create new chat (positioned on the left like Telegram)

### 2. Friends in LС (Left Sidebar)

Friends are displayed in the left sidebar with:
- Avatar image
- Display name or username
- Online status indicator (green dot)
- Last message preview
- Unread message badge

### 3. Mobile Responsive

The GUI adapts to mobile devices:
- Sidebar slides in/out on small screens (<768px)
- Burger menu button appears for navigation
- Message bubbles adjust width for readability
- Touch-friendly buttons and controls

### 4. User Tagging (@mentions)

Click the `@` button in the chat header to:
- See a dropdown list of users
- Click to insert @username into message
- Mentions are highlighted in messages

### 5. Bot Creation (@botcreatr)

Users can create custom bots:
1. Click `+` button in Chats section
2. Select "Create Bot" tab
3. Fill in bot details:
   - Username (starts with @)
   - Display name
   - Bio
   - Avatar (optional)
4. Receive API token for bot control
5. Use Bot API at `http://localhost:5001`

## API Endpoints Added

### Main Server (Port 5000)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/friends` | GET | Get user's friends list |
| `/api/chats` | GET | Get recent chats for sidebar |
| `/api/messages/private/<id>` | GET | Get private messages |
| `/api/messages/group/<id>` | GET | Get group messages |
| `/api/send_message` | POST | Send private message |
| `/api/send_group_message` | POST | Send group message |
| `/api/typing` | POST | Typing indicator |
| `/api/online` | GET | Update online status |
| `/api/upload_file` | POST | Upload file to chat |
| `/api/notifications` | GET | Get notifications |
| `/api/group/<id>` | GET | Get group info |

### Bot API Server (Port 5001)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/bot/create` | POST | Create new bot |
| `/api/bot/me` | GET | Get bot info |
| `/api/bot/update` | POST | Update bot config |
| `/api/bot/send` | POST | Send message as bot |
| `/api/bot/messages` | GET | Poll messages for bot |
| `/api/bots/list/<owner_id>` | GET | List user's bots |
| `/api/bot/delete` | POST | Deactivate bot |

## Usage Instructions

### Starting the Servers

1. **Main Chat Server** (Port 5000):
```bash
python server.py
```

2. **Bot API Server** (Port 5001):
```bash
cd bot_api
python bot_server.py
```

### Using the Interface

1. **Login/Register**: Navigate to `http://localhost:5000`
2. **View Friends**: Friends appear in left sidebar under "Messages"
3. **Start Chat**: Click on a friend or use `+` button
4. **Send Message**: Type in input bar and press Enter or click Send
5. **Tag Users**: Click `@` button to mention users
6. **Upload Files**: Click 📎 button to attach files
7. **Use Emoji**: Click 😊 button for emoji picker
8. **Create Bot**: Click `+` → "Create Bot" tab

### Bot Development

See `BOT_API_DOCUMENTATION.md` for complete Bot API documentation.

Example Python bot:
```python
import requests

TOKEN = "bot_your_token_here"
HEADERS = {"X-Bot-Token": TOKEN}

# Send message
requests.post("http://localhost:5001/api/bot/send",
    headers=HEADERS,
    json={"user_id": 5, "content": "Hello!"}
)

# Poll messages
resp = requests.get("http://localhost:5001/api/bot/messages",
    headers=HEADERS
)
for msg in resp.json():
    print(f"From {msg['from_user']['username']}: {msg['content']}")
```

## CSS Classes Added

```css
.list-section-title      /* Section headers in sidebar */
.group-badge             /* Group chat indicator */
.mention                 /* @mention styling */
.notif-item              /* Notification items */
.bot-creator-badge       /* Bot creator special badge */
.api-doc-link            /* API documentation link */
```

## JavaScript Functions

```javascript
loadFriends()            // Load and render friends list
openChat(id, type)       // Open chat with user/group
renderMessages()         // Render message bubbles with avatars
toggleUserTags()         // Show/hide user tags dropdown
insertMention(username)  // Insert @mention into input
createBot()              // Create new bot
toggleSidebar()          // Toggle sidebar on mobile
switchTab(tabName)       // Switch sidebar tabs
```

## Browser Compatibility

- Chrome/Edge (recommended)
- Firefox
- Safari
- Mobile browsers (iOS Safari, Chrome Mobile)

## Future Enhancements

- WebSocket support for real-time messaging
- Voice messages
- Video calls
- Stickers and GIFs
- Message reactions
- Chat folders
- Dark/light theme toggle
- Multi-language support
