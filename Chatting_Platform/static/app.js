/**
 * ChatRoom - WhatsApp-style real-time messaging
 */

// ──────────────────────────────────────────────────────────────────────────
// Safe localStorage helpers
// ──────────────────────────────────────────────────────────────────────────
function safeSetStorage(key, value) {
    try { localStorage.setItem(key, value); } catch (e) { /* blocked */ }
}
function safeGetStorage(key) {
    try { return localStorage.getItem(key); } catch (e) { return null; }
}

// ──────────────────────────────────────────────────────────────────────────
// App State
// ──────────────────────────────────────────────────────────────────────────
const AppState = {
    currentUser: null,
    token: null,
    currentChat: null,
    users: [],
    socket: null,
    isConnected: false,
    unreadCounts: {},
    lastMessages: {},
    typingTimers: {},
    audioCtx: null,
};

// ──────────────────────────────────────────────────────────────────────────
// DOM helpers
// ──────────────────────────────────────────────────────────────────────────
const El = {
    loginScreen:      () => document.getElementById("login-screen"),
    mainApp:          () => document.getElementById("main-app"),
    loginError:       () => document.getElementById("login-error"),
    usersList:        () => document.getElementById("users-list"),
    chatEmpty:        () => document.getElementById("chat-empty"),
    messagesArea:     () => document.getElementById("messages-area"),
    messageInputArea: () => document.getElementById("message-input-area"),
    messageInput:     () => document.getElementById("message-input"),
    messageForm:      () => document.getElementById("message-form"),
    searchInput:      () => document.getElementById("search-input"),
    chatHeader:       () => document.getElementById("chat-header"),
    headerAvatar:     () => document.getElementById("header-avatar"),
    headerName:       () => document.getElementById("header-name"),
    headerStatus:     () => document.getElementById("header-status"),
    typingIndicator:  () => document.getElementById("typing-indicator"),
    toastContainer:   () => document.getElementById("toast-container"),
};

// ──────────────────────────────────────────────────────────────────────────
// Boot
// ──────────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
    const params      = new URLSearchParams(window.location.search);
    const tokenURL    = params.get("token");
    const userIdURL   = params.get("user_id");
    const userNameURL = params.get("user_name");

    const token    = tokenURL    || safeGetStorage("chat_token");
    const userId   = userIdURL   || safeGetStorage("chat_user_id");
    const userName = userNameURL || safeGetStorage("chat_user_name");

    if (token && userId) {
        AppState.token = token;
        AppState.currentUser = { id: userId, name: userName };
        safeSetStorage("chat_token",     token);
        safeSetStorage("chat_user_id",   userId);
        safeSetStorage("chat_user_name", userName);
        if (tokenURL) window.history.replaceState({}, "", window.location.pathname);
        initializeApp();
    } else {
        showPage("login");
    }

    El.searchInput()?.addEventListener("input", e => renderUsersList(e.target.value));
    El.messageForm()?.addEventListener("submit", sendMessage);
    El.messageInput()?.addEventListener("input", handleTypingInput);
});

// ──────────────────────────────────────────────────────────────────────────
// Auth
// ──────────────────────────────────────────────────────────────────────────
function loginWithCognito() { window.location.href = "/auth/login"; }

function logout() {
    if (!confirm("Logout?")) return;
    AppState.socket?.disconnect();
    safeSetStorage("chat_token", "");
    safeSetStorage("chat_user_id", "");
    safeSetStorage("chat_user_name", "");
    fetch("/auth/logout", { method: "POST", headers: authHeader() }).finally(() => showPage("login"));
}

function authHeader() {
    return { "Authorization": "Bearer " + AppState.token, "Content-Type": "application/json" };
}

// ──────────────────────────────────────────────────────────────────────────
// Initialization
// ──────────────────────────────────────────────────────────────────────────
async function initializeApp() {
    try {
        const res = await fetch("/api/auth/verify", { headers: authHeader() });
        if (!res.ok) throw new Error("Token invalid");
        const data = await res.json();
        AppState.currentUser = data.user;
        showPage("chat");
        await loadUsers();
        initializeSocket();
    } catch (err) {
        console.error("Init failed:", err);
        showPage("login");
    }
}

// ──────────────────────────────────────────────────────────────────────────
// Socket.IO
// ──────────────────────────────────────────────────────────────────────────
function initializeSocket() {
    AppState.socket = io({
        query:                { token: AppState.token },
        transports:           ["polling"],
        upgrade:              false,
        reconnection:         true,
        reconnectionDelay:    1500,
        reconnectionAttempts: 10,
    });

    AppState.socket.on("connect", () => {
        AppState.isConnected = true;
        updateConnectionDot(true);
    });

    AppState.socket.on("disconnect", () => {
        AppState.isConnected = false;
        updateConnectionDot(false);
    });

    AppState.socket.on("users_list", data => {
        (data.users || []).forEach(su => {
            const ex = AppState.users.find(u => u.id === su.id);
            if (ex) { ex.is_online = true; }
            else { AppState.users.push({ ...su, is_online: true }); }
        });
        renderUsersList();
    });

    AppState.socket.on("user_online", data => {
        let user = AppState.users.find(u => u.id === data.user_id);
        if (user) { user.is_online = true; user.name = data.name; }
        else { AppState.users.push({ id: data.user_id, name: data.name, email: data.email, is_online: true }); }
        renderUsersList();
        refreshHeaderStatus();
    });

    AppState.socket.on("user_offline", data => {
        const user = AppState.users.find(u => u.id === data.user_id);
        if (user) { user.is_online = false; renderUsersList(); refreshHeaderStatus(); }
    });

    AppState.socket.on("new_message", msg => onNewMessage(msg));
    AppState.socket.on("user_typing", data => onUserTyping(data));
}

// ──────────────────────────────────────────────────────────────────────────
// Users list
// ──────────────────────────────────────────────────────────────────────────
async function loadUsers() {
    try {
        const res = await fetch("/api/users", { headers: authHeader() });
        if (!res.ok) return;
        const data = await res.json();
        AppState.users = (data.users || []).map(u => ({ ...u, is_online: true }));
        renderUsersList();
    } catch (e) { console.error("loadUsers:", e); }
}

function renderUsersList(filter = "") {
    const container = El.usersList();
    if (!container) return;

    let list = AppState.users;
    if (filter) {
        const f = filter.toLowerCase();
        list = list.filter(u => u.name.toLowerCase().includes(f) || (u.email||"").toLowerCase().includes(f));
    }

    if (list.length === 0) {
        container.innerHTML = '<div class="empty-list"><i class="fas fa-users fa-2x mb-2 text-muted"></i><p class="text-muted mb-0">' + (filter ? "No users found" : "No other users online") + '</p></div>';
        return;
    }

    container.innerHTML = list.map(user => {
        const unread   = AppState.unreadCounts[user.id] || 0;
        const chatId   = makeChatId(AppState.currentUser.id, user.id);
        const lastMsg  = AppState.lastMessages[chatId];
        const isActive = AppState.currentChat && AppState.currentChat.other_user_id === user.id;
        const initial  = (user.name || "?").charAt(0).toUpperCase();
        const color    = avatarColor(user.id);

        return '<div class="user-item' + (isActive ? " active" : "") + '" onclick="openChat(\'' + user.id + '\')">' +
            '<div class="avatar-wrap">' +
                '<div class="avatar" style="background:' + color + '">' + initial + '</div>' +
                '<span class="online-dot ' + (user.is_online ? "online" : "offline") + '"></span>' +
            '</div>' +
            '<div class="user-info">' +
                '<div class="user-top">' +
                    '<span class="user-name">' + escHtml(user.name) + '</span>' +
                    '<span class="msg-time">' + (lastMsg ? fmtTime(lastMsg.timestamp) : "") + '</span>' +
                '</div>' +
                '<div class="user-bottom">' +
                    '<span class="last-msg">' + (lastMsg ? escHtml(lastMsg.content) : (user.is_online ? "Online" : "Offline")) + '</span>' +
                    (unread ? '<span class="badge-count">' + (unread > 99 ? "99+" : unread) + '</span>' : "") +
                '</div>' +
            '</div>' +
        '</div>';
    }).join("");
}

// ──────────────────────────────────────────────────────────────────────────
// Open / load a chat
// ──────────────────────────────────────────────────────────────────────────
async function openChat(userId) {
    try {
        const res = await fetch("/api/chats/" + userId, { method: "POST", headers: authHeader() });
        if (!res.ok) throw new Error("Failed");
        const chatData = await res.json();
        AppState.currentChat = chatData;
        AppState.unreadCounts[userId] = 0;

        renderUsersList();
        renderChatHeader();

        El.chatEmpty()?.classList.add("d-none");
        El.messagesArea()?.classList.remove("d-none");
        El.messageInputArea()?.classList.remove("d-none");
        El.chatHeader()?.classList.remove("d-none");
        El.typingIndicator()?.classList.add("d-none");

        await loadMessages();
        El.messageInput()?.focus();
    } catch (e) {
        console.error("openChat:", e);
        showToast("Failed to open chat", "error");
    }
}

async function loadMessages() {
    if (!AppState.currentChat) return;
    try {
        const res = await fetch("/api/chats/" + AppState.currentChat.id + "/messages?per_page=50", { headers: authHeader() });
        if (!res.ok) return;
        const data = await res.json();
        const msgs = data.messages || [];

        const area = El.messagesArea();
        if (!area) return;
        area.innerHTML = "";

        let lastDate = null;
        msgs.forEach(msg => {
            const msgDate = new Date(msg.created_at).toDateString();
            if (msgDate !== lastDate) {
                lastDate = msgDate;
                const sep = document.createElement("div");
                sep.className = "date-separator";
                sep.textContent = fmtDateSep(msg.created_at);
                area.appendChild(sep);
            }
            area.appendChild(buildMsgEl(msg));
        });

        scrollToBottom(false);
    } catch (e) { console.error("loadMessages:", e); }
}

// ──────────────────────────────────────────────────────────────────────────
// Send message
// ──────────────────────────────────────────────────────────────────────────
function sendMessage(event) {
    event.preventDefault();
    const input = El.messageInput();
    const content = input && input.value.trim();
    if (!content || !AppState.currentChat || !AppState.currentChat.other_user_id || !AppState.socket) return;

    AppState.socket.emit("message", {
        recipient_id: AppState.currentChat.other_user_id,
        content: content,
    });

    input.value = "";
    input.focus();

    clearTimeout(typingDebounce);
    AppState.socket.emit("typing", { recipient_id: AppState.currentChat.other_user_id, is_typing: false });
}

// ──────────────────────────────────────────────────────────────────────────
// Incoming message handler
// ──────────────────────────────────────────────────────────────────────────
function onNewMessage(msg) {
    const senderId = msg.sender && msg.sender.id;
    const chatId   = msg.session_id;

    AppState.lastMessages[chatId] = {
        content:   msg.content,
        timestamp: msg.created_at,
    };

    const isCurrentChat = AppState.currentChat && AppState.currentChat.id === chatId;

    if (isCurrentChat) {
        const area = El.messagesArea();
        if (area) { area.appendChild(buildMsgEl(msg)); scrollToBottom(true); }
        clearTyping(senderId);
    } else {
        if (senderId && senderId !== AppState.currentUser.id) {
            AppState.unreadCounts[senderId] = (AppState.unreadCounts[senderId] || 0) + 1;
            playNotificationSound();
            const user = AppState.users.find(u => u.id === senderId);
            showToast((user ? user.name : "Someone") + ": " + msg.content, "message");
        }
    }

    renderUsersList();
}

// ──────────────────────────────────────────────────────────────────────────
// Typing
// ──────────────────────────────────────────────────────────────────────────
var typingDebounce = null;

function handleTypingInput() {
    if (!AppState.currentChat || !AppState.socket) return;
    AppState.socket.emit("typing", { recipient_id: AppState.currentChat.other_user_id, is_typing: true });
    clearTimeout(typingDebounce);
    typingDebounce = setTimeout(function() {
        if (AppState.socket && AppState.currentChat) {
            AppState.socket.emit("typing", { recipient_id: AppState.currentChat.other_user_id, is_typing: false });
        }
    }, 2000);
}

function onUserTyping(data) {
    var user_id   = data.user_id;
    var is_typing = data.is_typing;
    if (!AppState.currentChat || AppState.currentChat.other_user_id !== user_id) return;
    var el = El.typingIndicator();
    if (!el) return;
    clearTimeout(AppState.typingTimers[user_id]);
    if (is_typing) {
        el.classList.remove("d-none");
        AppState.typingTimers[user_id] = setTimeout(function() { el.classList.add("d-none"); }, 4000);
    } else {
        el.classList.add("d-none");
    }
}

function clearTyping(userId) {
    clearTimeout(AppState.typingTimers[userId]);
    if (AppState.currentChat && AppState.currentChat.other_user_id === userId) {
        El.typingIndicator() && El.typingIndicator().classList.add("d-none");
    }
}

// ──────────────────────────────────────────────────────────────────────────
// Build message DOM element
// ──────────────────────────────────────────────────────────────────────────
function buildMsgEl(msg) {
    const isOwn   = msg.sender && msg.sender.id === AppState.currentUser.id;
    const time    = fmtMsgTime(msg.created_at);
    const color   = (msg.sender && msg.sender.avatar_color) || avatarColor((msg.sender && msg.sender.id) || "");
    const initial = (msg.sender && msg.sender.name || "?").charAt(0).toUpperCase();

    const wrap = document.createElement("div");
    wrap.className = "msg-row " + (isOwn ? "own" : "other");
    wrap.innerHTML =
        (!isOwn ? '<div class="msg-avatar" style="background:' + color + '">' + initial + '</div>' : "") +
        '<div class="msg-bubble ' + (isOwn ? "bubble-own" : "bubble-other") + '">' +
            '<div class="msg-text">' + escHtml(msg.content) + '</div>' +
            '<div class="msg-meta">' +
                '<span class="msg-time">' + time + '</span>' +
                (isOwn ? '<span class="msg-tick"><i class="fas fa-check-double"></i></span>' : "") +
            '</div>' +
        '</div>';
    return wrap;
}

// ──────────────────────────────────────────────────────────────────────────
// Chat header
// ──────────────────────────────────────────────────────────────────────────
function renderChatHeader() {
    var chat = AppState.currentChat;
    if (!chat) return;
    var userId  = chat.other_user_id;
    var name    = chat.other_user_name || "Unknown";
    var user    = AppState.users.find(function(u) { return u.id === userId; });
    var online  = user ? user.is_online : false;
    var color   = avatarColor(userId);
    var initial = name.charAt(0).toUpperCase();

    var ha = El.headerAvatar();
    var hn = El.headerName();
    var hs = El.headerStatus();
    if (ha) ha.innerHTML = '<div class="avatar avatar-lg" style="background:' + color + '">' + initial + '</div>';
    if (hn) hn.textContent = name;
    if (hs) hs.innerHTML =
        '<span class="online-dot-sm ' + (online ? "online" : "offline") + '"></span>' +
        (online ? "Online" : "Offline");
}

function refreshHeaderStatus() {
    if (!AppState.currentChat) return;
    var user = AppState.users.find(function(u) { return u.id === AppState.currentChat.other_user_id; });
    if (!user) return;
    var hs = El.headerStatus();
    if (hs) hs.innerHTML =
        '<span class="online-dot-sm ' + (user.is_online ? "online" : "offline") + '"></span>' +
        (user.is_online ? "Online" : "Offline");
}

// ──────────────────────────────────────────────────────────────────────────
// Profile modal
// ──────────────────────────────────────────────────────────────────────────
function showProfile() {
    var user = AppState.currentUser;
    if (!user) return;
    document.getElementById("profile-name").textContent  = user.name  || "";
    document.getElementById("profile-email").textContent = user.email || "";
    document.getElementById("profile-avatar").innerHTML  =
        '<div class="avatar avatar-xl" style="background:' + avatarColor(user.id) + '">' +
        (user.name || "?").charAt(0).toUpperCase() + '</div>';
    new bootstrap.Modal(document.getElementById("profileModal")).show();
}

// ──────────────────────────────────────────────────────────────────────────
// Page control
// ──────────────────────────────────────────────────────────────────────────
function showPage(page) {
    if (page === "login") {
        El.loginScreen() && El.loginScreen().classList.remove("d-none");
        El.mainApp()     && El.mainApp().classList.add("d-none");
    } else {
        El.loginScreen() && El.loginScreen().classList.add("d-none");
        El.mainApp()     && El.mainApp().classList.remove("d-none");
    }
}

function updateConnectionDot(online) {
    var dot = document.getElementById("connection-dot");
    if (dot) dot.className = "connection-dot " + (online ? "online" : "offline");
}

function scrollToBottom(smooth) {
    var area = El.messagesArea();
    if (!area) return;
    area.scrollTo({ top: area.scrollHeight, behavior: smooth ? "smooth" : "instant" });
}

// ──────────────────────────────────────────────────────────────────────────
// Toast notifications
// ──────────────────────────────────────────────────────────────────────────
function showToast(message, type) {
    var container = El.toastContainer();
    if (!container) return;
    var toast = document.createElement("div");
    toast.className = "chat-toast toast-" + (type || "info");
    toast.innerHTML = (type === "message" ? '<i class="fas fa-comment-dots me-2"></i>' : '<i class="fas fa-info-circle me-2"></i>') +
        "<span>" + escHtml(message) + "</span>";
    container.appendChild(toast);
    requestAnimationFrame(function() { toast.classList.add("show"); });
    setTimeout(function() {
        toast.classList.remove("show");
        setTimeout(function() { toast.remove(); }, 400);
    }, 4000);
}

// ──────────────────────────────────────────────────────────────────────────
// Notification sound
// ──────────────────────────────────────────────────────────────────────────
function playNotificationSound() {
    try {
        if (!AppState.audioCtx) AppState.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        var ctx  = AppState.audioCtx;
        var osc  = ctx.createOscillator();
        var gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.frequency.setValueAtTime(830, ctx.currentTime);
        osc.frequency.setValueAtTime(680, ctx.currentTime + 0.1);
        gain.gain.setValueAtTime(0.12, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.35);
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + 0.35);
    } catch(e) { /* audio blocked */ }
}

// ──────────────────────────────────────────────────────────────────────────
// Utilities
// ──────────────────────────────────────────────────────────────────────────
function makeChatId(a, b) {
    var sorted = [a, b].slice().sort();
    return "('" + sorted[0] + "', '" + sorted[1] + "')";
}

function avatarColor(id) {
    var colors = ["#e74c3c","#e67e22","#f39c12","#27ae60","#16a085","#2980b9","#8e44ad","#2c3e50","#c0392b","#1abc9c"];
    var hash = 0;
    for (var i = 0; i < (id||"").length; i++) hash = ((hash * 31) + (id||"").charCodeAt(i)) | 0;
    return colors[Math.abs(hash) % colors.length];
}

function escHtml(text) {
    if (!text) return "";
    var d = document.createElement("div");
    d.textContent = text;
    return d.innerHTML;
}

function fmtMsgTime(ts) {
    if (!ts) return "";
    return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function fmtTime(ts) {
    if (!ts) return "";
    var d   = new Date(ts);
    var now = new Date();
    var diff = now - d;
    if (diff < 60000)      return "now";
    if (diff < 86400000)   return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    if (diff < 7*86400000) return d.toLocaleDateString([], { weekday: "short" });
    return d.toLocaleDateString([], { day: "2-digit", month: "short" });
}

function fmtDateSep(ts) {
    var d   = new Date(ts);
    var now = new Date();
    if (d.toDateString() === now.toDateString()) return "Today";
    var yes = new Date(now); yes.setDate(now.getDate() - 1);
    if (d.toDateString() === yes.toDateString()) return "Yesterday";
    return d.toLocaleDateString([], { day: "numeric", month: "long", year: "numeric" });
}
