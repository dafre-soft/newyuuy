# YuuY Chat - Documentation

## Overview
YuuY Chat is a modern real-time messaging platform built with Flask and SQLite. It features direct messaging, group chats, global channels, user profiles, walls, subscriptions, and an admin panel.

## Features

### Core Features
- **User Authentication**: Register, login, logout with session management
- **Direct Messages (DM)**: Private conversations between friends
- **Group Chats**: Create and manage group conversations
- **Global Channels**: Public channels for announcements
- **User Profiles**: Customizable profiles with avatars, bio, theme colors
- **Friend System**: Send/accept/decline friend requests
- **Subscriptions**: Follow users to see their wall posts in your feed
- **Wall Posts**: Post text, images, and files on user walls
- **Custom Pages**: Create custom HTML pages
- **Admin Panel**: User management, bans, role assignment

### Technical Features
- Real-time message polling (2-second intervals)
- File uploads (images, audio, documents) up to 1GB
- SQLite database with WAL mode for performance
- Responsive design (mobile-friendly)
- Theme customization per user
- Online status tracking
- Message read receipts

## Installation

### Prerequisites
- Python 3.8+
- pip package manager

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd <repository-directory>
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the server:
```bash
python server.py
```

4. Open your browser and navigate to:
```
http://localhost:5000
```

## Configuration

The server configuration is located at the top of `server.py`:

```python
app.secret_key = secrets.token_hex(32)  # Session secret
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # Max upload: 1GB
UPLOAD_FOLDER = 'uploads'  # Upload directory
STATIC_FOLDER = 'static'   # Static files directory
DB_PATH = 'chat_database.db'  # Database file
```

## API Endpoints

### Authentication
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/register` | POST | Register new user |
| `/login` | POST | User login |
| `/logout` | GET | User logout |

### User Management
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/me` | GET | Get current user info |
| `/api/user/<id>` | GET | Get user by ID |
| `/api/update_profile` | POST | Update profile settings |
| `/api/all_users` | GET | Get all users |

### Friends & Subscriptions
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/friend_action` | POST | Send/accept/decline friend requests |
| `/api/notifications` | GET | Get friend request notifications |
| `/api/subscribe/<id>` | POST | Subscribe to a user |
| `/api/unsubscribe/<id>` | POST | Unsubscribe from a user |

### Messaging
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chats` | GET | Get all chats (private, groups, channels) |
| `/api/messages/<type>/<id>` | GET | Get messages for a chat |
| `/api/send_message` | POST | Send a message |
| `/api/upload_file` | POST | Upload a file |

### Groups
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/create_group` | POST | Create a new group |
| `/api/group_members/<id>` | GET | Get group members |
| `/api/join_group/<id>` | POST | Join a group |
| `/api/leave_group/<id>` | POST | Leave a group |

### Wall & Feed
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/wall/<id>` | GET | Get user wall posts |
| `/api/post_wall` | POST | Post on a user's wall |
| `/api/feed` | GET | Get subscription feed |

### Admin
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin` | GET | Admin panel dashboard |
| `/api/admin/users` | GET | Get all users (admin) |
| `/api/admin/ban/<id>` | POST | Ban a user |
| `/api/admin/unban/<id>` | POST | Unban a user |
| `/api/admin/set_role/<id>` | POST | Set user role |

## Bot API

The server includes a RESTful Bot API for external integrations (e.g., Telegram bots, Discord bots, custom clients).

### Bot API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/bot/api/login` | POST | Authenticate bot/user |
| `/bot/api/get_me` | GET | Get authenticated user info |
| `/bot/api/get_chats` | GET | Get user's chats |
| `/bot/api/get_messages` | GET | Get messages from a chat |
| `/bot/api/send_message` | POST | Send a message |
| `/bot/api/get_friends` | GET | Get user's friends list |
| `/bot/api/send_friend_request` | POST | Send friend request |

### Bot API Usage Example

```python
import requests

BASE_URL = "http://localhost:5000/bot/api"

# Login
response = requests.post(f"{BASE_URL}/login", json={
    "username": "myuser",
    "password": "mypassword"
})
token = response.json()["token"]

headers = {"Authorization": f"Bearer {token}"}

# Get friends
friends = requests.get(f"{BASE_URL}/get_friends", headers=headers).json()

# Send message
requests.post(f"{BASE_URL}/send_message", headers=headers, json={
    "chat_type": "private",
    "target_id": 123,
    "content": "Hello!",
    "type": "text"
})
```

## Database Schema

### Tables
- `users` - User accounts and profiles
- `friendships` - Friend relationships
- `subscriptions` - User subscriptions
- `messages` - All messages (DM, group, channel, global)
- `groups` - Group definitions
- `group_members` - Group memberships
- `global_channels` - Admin channels
- `wall_posts` - Wall posts
- `custom_pages` - Custom HTML pages

## File Structure

```
/workspace/
├── server.py           # Main application
├── requirements.txt    # Python dependencies
├── uploads/            # Uploaded files
├── static/             # Static assets (avatars, favicon)
└── chat_database.db    # SQLite database
```

## Security Considerations

- Passwords are hashed using SHA-256
- Session-based authentication
- SQL injection protection via parameterized queries
- File upload validation (extension checking)
- Admin role-based access control
- Ban system for moderation

## Customization

### Theme Colors
Users can customize:
- Background color (`bg_color`)
- Accent/theme color (`theme_color`)

### Default Avatar
A default avatar is automatically generated if none exists at `/static/default_avatar.png`.

## Troubleshooting

### Database Issues
If you encounter database errors, delete `chat_database.db` and restart the server to recreate it.

### Upload Issues
Ensure the `uploads/` directory has write permissions.

### Port Already in Use
Change the port in `server.py`:
```python
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
```

## License

This project is provided as-is for educational and personal use.

## Support

For issues or questions, please check the code comments or create an issue in the repository.
