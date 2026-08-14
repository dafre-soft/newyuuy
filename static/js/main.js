/**
 * YuuY Chat - Main JavaScript (Telegram-style GUI)
 * Mobile-responsive chat interface with friends list on left sidebar
 */

// Global state
window.currentUser = null;
window.currentChatId = null;
window.currentChatType = null;
window.allUsers = [];
window.friends = [];
window.lastMessageId = 0;
window.pollingInterval = null;
window.typingTimeout = null;
window.isMobile = window.innerWidth < 768;

// Emoji list
const EMOJIS = ['😀','😂','😍','🥰','😎','🤔','😢','😡','👍','👎','🎉','❤️','🔥','👋','🙏','💪','🤣','😊','🥳','😭','😱','🤝','✅','❌','⭐','📌','🔔','💬','📷','🎵'];

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    loadCurrentUser();
    setupEventListeners();
    initEmojiPicker();
    
    if (window.innerWidth < 768) {
        document.querySelector('.sidebar').style.transform = 'translateX(-100%)';
        document.querySelector('.burger-menu').style.display = 'block';
    }
});

async function loadCurrentUser() {
    try {
        const res = await fetch('/api/me');
        if (res.ok) {
            window.currentUser = await res.json();
            loadFriends();
            loadChats();
            updateOnlineStatus(true);
        } else {
            window.location.href = '/login';
        }
    } catch (e) {
        console.error('Failed to load user:', e);
        window.location.href = '/login';
    }
}

function setupEventListeners() {
    window.addEventListener('resize', () => {
        window.isMobile = window.innerWidth < 768;
        if (!window.isMobile) {
            document.querySelector('.sidebar').style.transform = '';
            document.querySelector('.burger-menu').style.display = 'none';
        }
    });
    
    document.getElementById('messageInput')?.addEventListener('input', handleTyping);
}

async function updateOnlineStatus(online) {
    if (!window.currentUser) return;
    try {
        await fetch(`/api/online?status=${online ? 1 : 0}`);
    } catch (e) {
        console.error('Failed to update online status:', e);
    }
}

async function loadFriends() {
    try {
        const res = await fetch('/api/friends');
        if (res.ok) {
            const data = await res.json();
            window.friends = data.friends || [];
            renderFriendsList();
        }
    } catch (e) {
        console.error('Failed to load friends:', e);
    }
}

function renderFriendsList() {
    const container = document.getElementById('chatList');
    if (!container) return;
    
    let html = '';
    
    if (window.friends.length > 0) {
        html += '<div class="list-section-title">Friends</div>';
        window.friends.forEach(friend => {
            html += `
                <div class="list-item" onclick="openChat(${friend.id}, 'private')" data-chat-id="${friend.id}">
                    <img src="${friend.avatar_url || '/static/default_avatar.png'}" alt="">
                    <div class="list-info">
                        <div class="list-name">
                            ${escapeHtml(friend.display_name || friend.username)}
                            ${friend.is_online ? '<span class="online-dot"></span>' : ''}
                        </div>
                        <div class="list-preview">Click to chat</div>
                    </div>
                </div>
            `;
        });
    }
    
    html += '<div class="list-section-title">Recent Chats</div>';
    html += `<div id="recentChatsList"></div>`;
    
    container.innerHTML = html;
    loadRecentChats();
}

async function loadRecentChats() {
    try {
        const res = await fetch('/api/chats');
        if (res.ok) {
            const chats = await res.json();
            renderRecentChats(chats);
        }
    } catch (e) {
        console.error('Failed to load chats:', e);
    }
}

function renderRecentChats(chats) {
    const container = document.getElementById('recentChatsList');
    if (!container) return;
    
    let html = '';
    chats.forEach(chat => {
        const isGroup = chat.chat_type === 'group';
        html += `
            <div class="list-item" onclick="openChat(${isGroup ? chat.target_id : chat.user_id}, '${chat.chat_type}')" data-chat-id="${chat.id}">
                <img src="${chat.avatar_url || '/static/default_avatar.png'}" alt="">
                <div class="list-info">
                    <div class="list-name">
                        ${escapeHtml(chat.name)}
                        ${!isGroup && chat.is_online ? '<span class="online-dot"></span>' : ''}
                        ${isGroup ? '<span class="group-badge">👥</span>' : ''}
                    </div>
                    <div class="list-preview">${escapeHtml(chat.last_message || 'No messages yet')}</div>
                </div>
                ${chat.unread_count > 0 ? `<span class="unread-badge">${chat.unread_count}</span>` : ''}
            </div>
        `;
    });
    
    container.innerHTML = html;
}

async function openChat(targetId, chatType) {
    window.currentChatId = targetId;
    window.currentChatType = chatType;
    
    document.querySelectorAll('.list-item').forEach(el => el.classList.remove('active'));
    const activeItem = document.querySelector(`[data-chat-id="${targetId}"]`);
    if (activeItem) activeItem.classList.add('active');
    
    document.getElementById('inputBar').style.display = 'flex';
    document.getElementById('emptyState').style.display = 'none';
    
    await loadChatHeader(targetId, chatType);
    await loadMessages(targetId, chatType);
    startMessagePolling();
    
    if (window.isMobile) {
        document.querySelector('.sidebar').style.transform = 'translateX(-100%)';
    }
    
    setTimeout(() => document.getElementById('messageInput')?.focus(), 100);
}

async function loadChatHeader(targetId, chatType) {
    try {
        let data;
        if (chatType === 'private') {
            const res = await fetch(`/api/user/${targetId}`);
            data = await res.json();
            
            document.getElementById('headerAvatar').src = data.avatar_url || '/static/default_avatar.png';
            document.getElementById('chatTitle').textContent = data.display_name || data.username;
            document.getElementById('chatStatus').textContent = data.is_online ? 'online' : 'offline';
            document.getElementById('btnViewProfile').style.display = 'block';
            document.getElementById('btnGroupSettings').style.display = 'none';
        } else {
            const res = await fetch(`/api/group/${targetId}`);
            data = await res.json();
            
            document.getElementById('headerAvatar').src = data.avatar_url || '/static/default_avatar.png';
            document.getElementById('chatTitle').textContent = data.name;
            document.getElementById('chatStatus').textContent = `${data.member_count} members`;
            document.getElementById('btnViewProfile').style.display = 'none';
            document.getElementById('btnGroupSettings').style.display = 'block';
        }
    } catch (e) {
        console.error('Failed to load chat header:', e);
    }
}

async function loadMessages(targetId, chatType) {
    try {
        const endpoint = chatType === 'private' 
            ? `/api/messages/private/${targetId}`
            : `/api/messages/group/${targetId}`;
        
        const res = await fetch(endpoint);
        if (res.ok) {
            const messages = await res.json();
            renderMessages(messages);
            window.lastMessageId = messages.length > 0 ? messages[messages.length - 1].id : 0;
        }
    } catch (e) {
        console.error('Failed to load messages:', e);
    }
}

function renderMessages(messages) {
    const container = document.getElementById('messagesContainer');
    if (!container) return;
    
    let html = '';
    let lastSenderId = null;
    
    messages.forEach(msg => {
        const isMine = msg.sender_id === window.currentUser.id;
        const showAvatar = msg.sender_id !== lastSenderId;
        
        if (showAvatar) {
            html += `
                <div class="msg-row ${isMine ? 'mine' : 'theirs'}">
                    <img src="${msg.sender_avatar || '/static/default_avatar.png'}" 
                         class="msg-avatar" 
                         onclick="openProfile(${msg.sender_id})"
                         alt="">
                    <div class="msg-bubble">
                        ${!isMine ? `<div class="msg-sender">${escapeHtml(msg.sender_name)}</div>` : ''}
                        <div>${formatMessageContent(msg.content)}</div>
                        <div class="msg-time">${formatTime(msg.timestamp)}</div>
                    </div>
                </div>
            `;
        } else {
            html += `
                <div class="msg-row ${isMine ? 'mine' : 'theirs'} no-avatar">
                    <div class="msg-bubble">
                        <div>${formatMessageContent(msg.content)}</div>
                        <div class="msg-time">${formatTime(msg.timestamp)}</div>
                    </div>
                </div>
            `;
        }
        
        lastSenderId = msg.sender_id;
    });
    
    container.innerHTML = html;
    scrollToBottom();
}

function formatMessageContent(content) {
    if (!content) return '';
    
    let formatted = escapeHtml(content);
    formatted = formatted.replace(/@(\w+)/g, '<span class="mention">@$1</span>');
    formatted = formatted.replace(
        /(https?:\/\/[^\s]+)/g, 
        '<a href="$1" target="_blank" rel="noopener">$1</a>'
    );
    
    return formatted;
}

async function sendMessage() {
    const input = document.getElementById('messageInput');
    const content = input.value.trim();
    
    if (!content || !window.currentChatId) return;
    
    try {
        const endpoint = window.currentChatType === 'private'
            ? '/api/send_message'
            : '/api/send_group_message';
        
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                target_id: window.currentChatId,
                content: content,
                type: 'text'
            })
        });
        
        if (res.ok) {
            input.value = '';
            await loadMessages(window.currentChatId, window.currentChatType);
            await loadChats();
        }
    } catch (e) {
        console.error('Failed to send message:', e);
    }
}

function handleTyping() {
    clearTimeout(window.typingTimeout);
    
    if (window.currentChatId) {
        fetch('/api/typing', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({target_id: window.currentChatId})
        }).catch(e => console.error('Typing indicator failed:', e));
    }
    
    window.typingTimeout = setTimeout(() => {}, 2000);
}

function startMessagePolling() {
    if (window.pollingInterval) clearInterval(window.pollingInterval);
    
    window.pollingInterval = setInterval(async () => {
        if (!window.currentChatId) return;
        
        try {
            const endpoint = window.currentChatType === 'private'
                ? `/api/messages/private/${window.currentChatId}?since_id=${window.lastMessageId}`
                : `/api/messages/group/${window.currentChatId}?since_id=${window.lastMessageId}`;
            
            const res = await fetch(endpoint);
            if (res.ok) {
                const newMessages = await res.json();
                if (newMessages.length > 0) {
                    await loadMessages(window.currentChatId, window.currentChatType);
                    window.lastMessageId = newMessages[newMessages.length - 1].id;
                    
                    if (document.hidden) {
                        playNotificationSound();
                    }
                }
            }
        } catch (e) {
            console.error('Polling failed:', e);
        }
    }, 2000);
}

async function loadAllUsers() {
    try {
        const res = await fetch('/api/all_users');
        if (res.ok) {
            window.allUsers = await res.json();
        }
    } catch (e) {
        console.error('Failed to load users:', e);
    }
}

async function openNewChatModal() {
    await loadAllUsers();
    document.getElementById('newChatModal').style.display = 'flex';
    document.getElementById('userSearchInput').value = '';
    document.getElementById('userSearchResults').innerHTML = '';
    showUserType('all');
}

async function searchUsers() {
    const query = document.getElementById('userSearchInput').value.toLowerCase();
    const filtered = window.allUsers.filter(u => 
        u.username.toLowerCase().includes(query) || 
        (u.display_name && u.display_name.toLowerCase().includes(query))
    );
    
    renderUserSearchResults(filtered);
}

function renderUserSearchResults(users) {
    const container = document.getElementById('userSearchResults');
    if (!container) return;
    
    let html = '';
    users.slice(0, 20).forEach(user => {
        html += `
            <div class="user-item" onclick="startChatWithUser(${user.id})">
                <img src="${user.avatar_url || '/static/default_avatar.png'}" alt="">
                <div class="user-item-info">
                    <div class="user-item-name">
                        ${escapeHtml(user.display_name || user.username)}
                        ${user.is_bot ? '<span class="bot-badge">BOT</span>' : ''}
                    </div>
                    <div class="user-item-username">@${user.username}</div>
                </div>
            </div>
        `;
    });
    
    container.innerHTML = html;
}

async function startChatWithUser(userId) {
    closeModal('newChatModal');
    await openChat(userId, 'private');
}

async function createBot() {
    const username = document.getElementById('botUsername').value.trim();
    const displayName = document.getElementById('botDisplayName').value.trim();
    const bio = document.getElementById('botBio').value.trim();
    const avatarFile = document.getElementById('botAvatar').files[0];
    
    if (!username || username.length < 3) {
        alert('Bot username must be at least 3 characters');
        return;
    }
    
    const formData = new FormData();
    formData.append('username', username.startsWith('@') ? username : '@' + username);
    formData.append('display_name', displayName || username);
    formData.append('bio', bio);
    if (avatarFile) formData.append('avatar', avatarFile);
    
    try {
        const res = await fetch('/api/bots/create', {
            method: 'POST',
            body: formData
        });
        
        const data = await res.json();
        
        if (res.ok && data.success) {
            document.getElementById('botTokenDisplay').textContent = data.api_token;
            document.getElementById('createBotModal').style.display = 'none';
            document.getElementById('botInfoModal').style.display = 'flex';
            await loadAllUsers();
        } else {
            alert(data.error || 'Failed to create bot');
        }
    } catch (e) {
        console.error('Failed to create bot:', e);
        alert('Failed to create bot');
    }
}

function copyBotToken() {
    const token = document.getElementById('botTokenDisplay').textContent;
    navigator.clipboard.writeText(token).then(() => {
        alert('Token copied to clipboard!');
    });
}

function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    if (sidebar.style.transform === 'translateX(-100%)') {
        sidebar.style.transform = '';
    } else {
        sidebar.style.transform = 'translateX(-100%)';
    }
}

function switchTab(tabName, tabElement) {
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    tabElement.classList.add('active');
    
    document.getElementById('chatsSection').style.display = tabName === 'chats' ? 'block' : 'none';
    document.getElementById('groupsSection').style.display = tabName === 'groups' ? 'block' : 'none';
    document.getElementById('feedSection').style.display = tabName === 'feed' ? 'block' : 'none';
    document.getElementById('pagesSection').style.display = tabName === 'pages' ? 'block' : 'none';
    
    if (tabName === 'groups') loadGroups();
    if (tabName === 'feed') loadFeed();
    if (tabName === 'pages') loadPages();
}

function filterChats() {
    const query = document.getElementById('chatSearch').value.toLowerCase();
    document.querySelectorAll('.list-item').forEach(item => {
        const text = item.textContent.toLowerCase();
        item.style.display = text.includes(query) ? 'flex' : 'none';
    });
}

function toggleEmojiPicker() {
    const picker = document.getElementById('emojiPicker');
    picker.style.display = picker.style.display === 'none' ? 'block' : 'none';
}

function initEmojiPicker() {
    const grid = document.querySelector('.emoji-grid');
    if (!grid) return;
    
    grid.innerHTML = EMOJIS.map(emoji => 
        `<span class="emoji-item" onclick="insertEmoji('${emoji}')">${emoji}</span>`
    ).join('');
}

function insertEmoji(emoji) {
    const input = document.getElementById('messageInput');
    input.value += emoji;
    input.focus();
    document.getElementById('emojiPicker').style.display = 'none';
}

function toggleUserTags() {
    const dropdown = document.getElementById('tagsDropdown');
    if (dropdown.style.display === 'none') {
        loadUserTags();
        dropdown.style.display = 'block';
    } else {
        dropdown.style.display = 'none';
    }
}

async function loadUserTags() {
    const container = document.getElementById('tagsList');
    if (!container) return;
    
    try {
        const res = await fetch('/api/all_users');
        if (res.ok) {
            const users = await res.json();
            container.innerHTML = users.slice(0, 15).map(u => `
                <div class="tag-item" onclick="insertMention('@${u.username}')">
                    <img src="${u.avatar_url || '/static/default_avatar.png'}" alt="">
                    <span>@${u.username}</span>
                </div>
            `).join('');
        }
    } catch (e) {
        console.error('Failed to load tags:', e);
    }
}

function insertMention(username) {
    const input = document.getElementById('messageInput');
    input.value += username + ' ';
    input.focus();
    document.getElementById('tagsDropdown').style.display = 'none';
}

async function handleFileUpload(input) {
    const files = input.files;
    if (!files.length || !window.currentChatId) return;
    
    for (let file of files) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('target_id', window.currentChatId);
        formData.append('chat_type', window.currentChatType);
        
        try {
            const res = await fetch('/api/upload_file', {
                method: 'POST',
                body: formData
            });
            
            if (res.ok) {
                await loadMessages(window.currentChatId, window.currentChatType);
            }
        } catch (e) {
            console.error('Upload failed:', e);
        }
    }
    
    input.value = '';
}

function handleKeyPress(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

function scrollToBottom() {
    const container = document.getElementById('messagesContainer');
    if (container) {
        container.scrollTop = container.scrollHeight;
    }
}

function formatTime(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function playNotificationSound() {
    const audio = new Audio('/uploads/notification.wav');
    audio.play().catch(e => console.log('Audio play failed:', e));
}

function openModal(modalId) {
    document.getElementById(modalId + 'Modal').style.display = 'flex';
    
    if (modalId === 'editProfile') {
        loadProfileData();
    }
}

function closeModal(modalId) {
    document.getElementById(modalId).style.display = 'none';
}

async function loadProfileData() {
    if (!window.currentUser) return;
    
    document.getElementById('editDisplayName').value = window.currentUser.display_name || '';
    document.getElementById('editBio').value = window.currentUser.bio || '';
    document.getElementById('editThemeColor').value = window.currentUser.theme_color || '#a78bfa';
    document.getElementById('editBgColor').value = window.currentUser.bg_color || '#0d0a1a';
}

async function saveProfile() {
    const formData = new FormData();
    formData.append('display_name', document.getElementById('editDisplayName').value);
    formData.append('bio', document.getElementById('editBio').value);
    formData.append('theme_color', document.getElementById('editThemeColor').value);
    formData.append('bg_color', document.getElementById('editBgColor').value);
    
    const avatarFile = document.getElementById('editAvatar').files[0];
    if (avatarFile) formData.append('avatar', avatarFile);
    
    try {
        const res = await fetch('/api/update_profile', {
            method: 'POST',
            body: formData
        });
        
        if (res.ok) {
            closeModal('editProfileModal');
            location.reload();
        }
    } catch (e) {
        console.error('Failed to save profile:', e);
    }
}

async function loadGroups() {}
async function loadFeed() {}
async function loadPages() {}

async function openProfile(userId) {
    try {
        const res = await fetch(`/api/user/${userId}`);
        if (res.ok) {
            const user = await res.json();
            
            document.getElementById('profileAvatar').src = user.avatar_url || '/static/default_avatar.png';
            document.getElementById('profileName').textContent = user.display_name || user.username;
            document.getElementById('profileBio').textContent = user.bio || 'No bio';
            document.getElementById('profileStats').textContent = `Joined: ${user.created_at}`;
            
            await loadWallPosts(userId);
            setupProfileActions(user);
            
            document.getElementById('userProfileModal').style.display = 'flex';
        }
    } catch (e) {
        console.error('Failed to load profile:', e);
    }
}

function setupProfileActions(user) {
    const container = document.getElementById('profileActions');
    if (!container) return;
    
    let html = '';
    
    if (user.id !== window.currentUser.id) {
        html += `<button class="btn-primary" onclick="openChat(${user.id}, 'private')">Message</button>`;
        
        if (user.friend_status === 'none') {
            html += `<button class="btn-secondary" onclick="sendFriendRequest(${user.id})">Add Friend</button>`;
        } else if (user.friend_status === 'received_request') {
            html += `<button class="btn-primary" onclick="acceptFriendRequest(${user.id})">Accept</button>`;
            html += `<button class="btn-secondary" onclick="declineFriendRequest(${user.id})">Decline</button>`;
        } else if (user.friend_status === 'friends') {
            html += `<button class="btn-secondary" onclick="unfriend(${user.id})">Unfriend</button>`;
        }
    }
    
    container.innerHTML = html;
}

async function sendFriendRequest(userId) { await performFriendAction('send_request', userId); }
async function acceptFriendRequest(userId) { await performFriendAction('accept', userId); }
async function declineFriendRequest(userId) { await performFriendAction('decline', userId); }
async function unfriend(userId) { await performFriendAction('unfriend', userId); }

async function performFriendAction(action, userId) {
    try {
        const res = await fetch('/api/friend_action', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({action, target_id: userId})
        });
        
        if (res.ok) {
            closeModal('userProfileModal');
            await loadFriends();
        }
    } catch (e) {
        console.error('Friend action failed:', e);
    }
}

async function loadWallPosts(userId) {}
async function postToWall() {}

async function createGroup() {
    const name = document.getElementById('groupName').value.trim();
    const description = document.getElementById('groupDescription').value.trim();
    
    if (!name) {
        alert('Group name is required');
        return;
    }
    
    try {
        const res = await fetch('/api/groups/create', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name, description})
        });
        
        if (res.ok) {
            closeModal('createGroupModal');
            loadGroups();
        }
    } catch (e) {
        console.error('Failed to create group:', e);
    }
}

async function openNotifications() {
    try {
        const res = await fetch('/api/notifications');
        if (res.ok) {
            const notifs = await res.json();
            renderNotifications(notifs);
            document.getElementById('notificationsModal').style.display = 'flex';
        }
    } catch (e) {
        console.error('Failed to load notifications:', e);
    }
}

function renderNotifications(notifications) {
    const container = document.getElementById('notifList');
    if (!container) return;
    
    if (notifications.length === 0) {
        container.innerHTML = '<p style="color: var(--sub);">No notifications</p>';
        return;
    }
    
    container.innerHTML = notifications.map(n => `
        <div class="notif-item">
            <div class="notif-content">${escapeHtml(n.content)}</div>
            <div class="notif-time">${formatTime(n.timestamp)}</div>
        </div>
    `).join('');
}

window.addEventListener('beforeunload', () => {
    updateOnlineStatus(false);
    if (window.pollingInterval) clearInterval(window.pollingInterval);
});
