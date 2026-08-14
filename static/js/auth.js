// Auth JavaScript
const isRegister = window.location.pathname.includes('register');
const mode = isRegister ? 'register' : 'login';

document.getElementById('authTitle').textContent = `YuuY ${mode.charAt(0).toUpperCase() + mode.slice(1)}`;
document.getElementById('authBtn').textContent = mode.charAt(0).toUpperCase() + mode.slice(1);
document.getElementById('authSwitch').innerHTML = isRegister 
    ? 'Have account? <a href="/login">Login</a>'
    : 'No account? <a href="/register">Register</a>';

document.getElementById('authForm').onsubmit = async (e) => {
    e.preventDefault();
    const username = document.getElementById('username').value.trim();
    const password = document.getElementById('password').value.trim();
    
    try {
        const res = await fetch(window.location.pathname, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        
        const data = await res.json();
        
        if (data.success) {
            window.location.href = data.redirect;
        } else {
            alert(data.error || 'Authentication failed');
        }
    } catch (err) {
        console.error('Auth error:', err);
        alert('Connection error. Please try again.');
    }
};
