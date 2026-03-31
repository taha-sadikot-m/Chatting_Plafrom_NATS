# ChatRoom API Documentation

Complete API reference for the ChatRoom messaging platform.

## Base URL

```
http://localhost:5000  (Development)
https://yourapp.com    (Production)
```

## Authentication

All API requests (except `/auth/*` endpoints) require a JWT token in the Authorization header:

```
Authorization: Bearer {jwt_token}
```

The token is obtained after successful Cognito authentication. WebSocket connections require the token as a query parameter: `?token={jwt_token}`

## Response Format

All API responses are JSON with the following structure:

**Success Response:**
```json
{
  "data": {...},
  "status": 200
}
```

**Error Response:**
```json
{
  "error": "Error message",
  "status": 400
}
```

## Endpoints

### Authentication Endpoints

#### 1. Login
Initiates the OAuth 2.0 login flow with AWS Cognito.

**Request:**
- Method: `GET`
- Path: `/auth/login`
- Auth: None

**Response:**
- Redirects to Cognito login page

**Example:**
```bash
curl -L http://localhost:5000/auth/login
```

#### 2. OAuth Callback
Handles the callback from Cognito after successful authentication.

**Request:**
- Method: `GET`
- Path: `/auth/callback`
- Query Parameters:
  - `code` (string): Authorization code from Cognito
  - `state` (string): State parameter for CSRF protection
  - `error` (string, optional): Error code if login failed

**Response:**
```json
{
  "token": "eyJhbGc...",
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "user_email": "user@example.com"
}
```

**Example:**
```bash
# Called automatically by Cognito, then redirected to app
curl -L "http://localhost:5000/auth/callback?code=.......&state=......."
```

#### 3. Logout
Logs out the current user and invalidates the session.

**Request:**
- Method: `POST`
- Path: `/auth/logout`
- Auth: Required
- Body: None

**Response:**
```json
{
  "ok": true,
  "logout_url": "https://yourdomain.auth.us-east-1.amazoncognito.com/logout?..."
}
```

**Example:**
```bash
curl -X POST http://localhost:5000/auth/logout \
  -H "Authorization: Bearer {token}"
```

#### 4. Verify Token
Verifies the current authentication token and returns user information.

**Request:**
- Method: `GET`
- Path: `/api/auth/verify`
- Auth: Required

**Response:**
```json
{
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "cognito_id": "us-east-1_xxxxx:12345678-1234-1234-1234-123456789012",
    "email": "user@example.com",
    "name": "John Doe",
    "avatar_color": "#3498db",
    "bio": "Software Engineer",
    "is_online": true,
    "last_seen": "2024-03-27T10:30:00",
    "created_at": "2024-01-15T08:20:00",
    "updated_at": "2024-03-27T10:30:00"
  },
  "authenticated": true
}
```

**Example:**
```bash
curl http://localhost:5000/api/auth/verify \
  -H "Authorization: Bearer {token}"
```

---

### User Endpoints

#### 1. Get All Users
Retrieves a list of all active users (excluding the current user).

**Request:**
- Method: `GET`
- Path: `/api/users`
- Auth: Required
- Query Parameters: None

**Response:**
```json
{
  "users": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440001",
      "name": "Alice Smith",
      "email": "alice@example.com",
      "avatar_color": "#2ecc71",
      "is_online": true,
      "bio": "Product Manager"
    },
    {
      "id": "550e8400-e29b-41d4-a716-446655440002",
      "name": "Bob Johnson",
      "email": "bob@example.com",
      "avatar_color": "#e74c3c",
      "is_online": false,
      "bio": null
    }
  ]
}
```

**Status Codes:**
- `200`: Success
- `401`: Unauthorized
- `500`: Server error

**Example:**
```bash
curl http://localhost:5000/api/users \
  -H "Authorization: Bearer {token}"
```

#### 2. Get User Details
Retrieves detailed information about a specific user.

**Request:**
- Method: `GET`
- Path: `/api/users/{user_id}`
- Auth: Required
- URL Parameters:
  - `user_id` (UUID): The user's unique identifier

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440001",
  "cognito_id": "us-east-1_xxxxx:uuid",
  "email": "alice@example.com",
  "name": "Alice Smith",
  "avatar_color": "#2ecc71",
  "bio": "Product Manager",
  "is_active": true,
  "is_online": true,
  "last_seen": "2024-03-27T10:30:00",
  "created_at": "2024-01-15T08:20:00",
  "updated_at": "2024-03-27T10:30:00"
}
```

**Status Codes:**
- `200`: Success
- `401`: Unauthorized
- `404`: User not found
- `500`: Server error

**Example:**
```bash
curl http://localhost:5000/api/users/550e8400-e29b-41d4-a716-446655440001 \
  -H "Authorization: Bearer {token}"
```

#### 3. Update User Profile
Updates the current user's profile information.

**Request:**
- Method: `PUT`
- Path: `/api/users/{user_id}`
- Auth: Required
- URL Parameters:
  - `user_id` (UUID): Must be the current user's ID
- Body:
```json
{
  "name": "John Doe",
  "bio": "Senior Software Engineer",
  "avatar_color": "#9b59b6"
}
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "cognito_id": "us-east-1_xxxxx:uuid",
  "email": "user@example.com",
  "name": "John Doe",
  "avatar_color": "#9b59b6",
  "bio": "Senior Software Engineer",
  "is_active": true,
  "is_online": true,
  "last_seen": "2024-03-27T10:35:00",
  "created_at": "2024-01-15T08:20:00",
  "updated_at": "2024-03-27T10:35:00"
}
```

**Status Codes:**
- `200`: Success
- `400`: Invalid data
- `401`: Unauthorized
- `403`: Cannot update other users' profiles
- `500`: Server error

**Example:**
```bash
curl -X PUT http://localhost:5000/api/users/550e8400-e29b-41d4-a716-446655440000 \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Doe",
    "bio": "Senior Software Engineer",
    "avatar_color": "#9b59b6"
  }'
```

---

### Chat Session Endpoints

#### 1. Get All Chat Sessions
Retrieves all chat sessions for the current user.

**Request:**
- Method: `GET`
- Path: `/api/chats`
- Auth: Required

**Response:**
```json
{
  "chat_sessions": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440003",
      "other_user": {
        "id": "550e8400-e29b-41d4-a716-446655440001",
        "name": "Alice Smith",
        "email": "alice@example.com",
        "avatar_color": "#2ecc71",
        "is_online": true
      },
      "last_message_at": "2024-03-27T10:25:00",
      "is_archived": false,
      "created_at": "2024-03-20T14:00:00",
      "updated_at": "2024-03-27T10:25:00"
    }
  ]
}
```

**Status Codes:**
- `200`: Success
- `401`: Unauthorized
- `500`: Server error

**Example:**
```bash
curl http://localhost:5000/api/chats \
  -H "Authorization: Bearer {token}"
```

#### 2. Get or Create Chat Session
Gets an existing chat session or creates a new one with another user.

**Request:**
- Method: `GET` or `POST`
- Path: `/api/chats/{recipient_id}`
- Auth: Required
- URL Parameters:
  - `recipient_id` (UUID): The other user's ID

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440003",
  "other_user": {
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "name": "Alice Smith",
    "email": "alice@example.com",
    "avatar_color": "#2ecc71",
    "is_online": true
  },
  "last_message_at": null,
  "is_archived": false,
  "created_at": "2024-03-27T10:30:00",
  "updated_at": "2024-03-27T10:30:00"
}
```

**Status Codes:**
- `200`: Success
- `400`: Invalid request (e.g., chatting with yourself)
- `401`: Unauthorized
- `404`: User not found
- `500`: Server error

**Example:**
```bash
# Create new chat
curl -X POST http://localhost:5000/api/chats/550e8400-e29b-41d4-a716-446655440001 \
  -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json"
```

#### 3. Get Chat Messages
Retrieves messages from a chat session with pagination.

**Request:**
- Method: `GET`
- Path: `/api/chats/{session_id}/messages`
- Auth: Required
- URL Parameters:
  - `session_id` (UUID): The chat session ID
- Query Parameters:
  - `page` (integer, default: 1): Page number
  - `per_page` (integer, default: 50): Messages per page

**Response:**
```json
{
  "messages": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440004",
      "session_id": "550e8400-e29b-41d4-a716-446655440003",
      "sender": {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "John Doe",
        "email": "user@example.com",
        "avatar_color": "#3498db"
      },
      "content": "Hey, how are you?",
      "message_type": "text",
      "is_edited": false,
      "edited_at": null,
      "created_at": "2024-03-27T10:25:00"
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 50,
    "total": 150,
    "pages": 3
  }
}
```

**Status Codes:**
- `200`: Success
- `401`: Unauthorized
- `403`: Access denied (not part of chat)
- `404`: Chat not found
- `500`: Server error

**Example:**
```bash
curl "http://localhost:5000/api/chats/550e8400-e29b-41d4-a716-446655440003/messages?page=1&per_page=50" \
  -H "Authorization: Bearer {token}"
```

---

### WebSocket Events

Connect to WebSocket at `/socket.io/` with query parameter `?token={jwt_token}`

#### Client → Server Events

##### 1. Connect
Automatically triggered when WebSocket connects. Include token in query parameters.

```javascript
const socket = io({
  query: {
    token: jwt_token
  }
});
```

##### 2. Send Message
Sends a message in a chat session.

**Event:** `message`
**Payload:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440003",
  "content": "Hello, how are you?"
}
```

**Example:**
```javascript
socket.emit('message', {
  session_id: 'session-uuid',
  content: 'Hello World'
});
```

##### 3. Typing Indicator
Emits typing status to other users.

**Event:** `typing`
**Payload:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440003",
  "is_typing": true
}
```

**Example:**
```javascript
socket.emit('typing', {
  session_id: 'session-uuid',
  is_typing: true
});
```

#### Server → Client Events

##### 1. Connect Confirmation
Confirms successful WebSocket connection.

**Event:** `connect`

##### 2. New Message
Broadcasts when a message is received.

**Event:** `new_message`
**Payload:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440004",
  "session_id": "550e8400-e29b-41d4-a716-446655440003",
  "sender": {
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "name": "Alice Smith",
    "email": "alice@example.com",
    "avatar_color": "#2ecc71"
  },
  "content": "Thanks, I'm doing well!",
  "message_type": "text",
  "is_edited": false,
  "edited_at": null,
  "created_at": "2024-03-27T10:26:00"
}
```

**Example:**
```javascript
socket.on('new_message', (message) => {
  console.log('New message:', message);
  // Add message to UI
});
```

##### 3. User Status Changed
Broadcasts when a user comes online/offline.

**Event:** `user_status_changed`
**Payload:**
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440001",
  "is_online": true,
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "name": "Alice Smith",
    "email": "alice@example.com",
    "avatar_color": "#2ecc71",
    "is_online": true
  }
}
```

**Example:**
```javascript
socket.on('user_status_changed', (data) => {
  console.log(`${data.user.name} is now ${data.is_online ? 'online' : 'offline'}`);
});
```

##### 4. User Typing
Broadcasts when a user is typing.

**Event:** `user_typing`
**Payload:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440003",
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "name": "Alice Smith"
  },
  "is_typing": true
}
```

**Example:**
```javascript
socket.on('user_typing', (data) => {
  if (data.is_typing) {
    console.log(`${data.user.name} is typing...`);
  }
});
```

##### 5. Error
Emitted when an error occurs.

**Event:** `error`
**Payload:**
```json
{
  "error": "Error message"
}
```

**Example:**
```javascript
socket.on('error', (data) => {
  console.error('WebSocket error:', data.error);
});
```

---

## Error Codes & Messages

| Status | Code | Message | Cause |
|--------|------|---------|-------|
| 400 | `bad_request` | Missing or invalid parameters | Malformed request |
| 401 | `unauthorized` | No authorization token | Missing/invalid token |
| 403 | `forbidden` | Access denied | User can't access resource |
| 404 | `not_found` | Resource not found | Invalid ID or missing resource |
| 500 | `server_error` | Internal server error | Server error |

---

## Rate Limiting

Currently not implemented but recommended for production:
- 100 requests per minute per IP
- 1000 messages per hour per user
- 10 WebSocket connections per user

---

## Testing the API

### Using cURL

```bash
# 1. Login
curl -L http://localhost:5000/auth/login

# 2. After redirect, you'll get a token
# Set TOKEN environment variable
export TOKEN="eyJhbGc..."

# 3. Get users
curl http://localhost:5000/api/users \
  -H "Authorization: Bearer $TOKEN"

# 4. Create chat
curl -X POST http://localhost:5000/api/chats/{recipient_id} \
  -H "Authorization: Bearer $TOKEN"
```

### Using JavaScript/Fetch

```javascript
// Setup
const token = localStorage.getItem('chat_token');

// Get all users
fetch('/api/users', {
  headers: {
    'Authorization': `Bearer ${token}`
  }
})
.then(r => r.json())
.then(data => console.log(data));

// Send message via WebSocket
const socket = io({
  query: { token }
});

socket.on('connect', () => {
  socket.emit('message', {
    session_id: 'chat-id',
    content: 'Hello!'
  });
});
```

### Using Python/Requests

```python
import requests

token = "eyJhbGc..."
headers = {"Authorization": f"Bearer {token}"}

# Get users
response = requests.get(
    "http://localhost:5000/api/users",
    headers=headers
)
print(response.json())
```

---

## Pagination

Message pagination uses offset/limit pattern:

```
GET /api/chats/{session_id}/messages?page=1&per_page=50
```

Response includes pagination metadata:
```json
{
  "messages": [...],
  "pagination": {
    "page": 1,
    "per_page": 50,
    "total": 150,
    "pages": 3
  }
}
```

---

**API Version:** 1.0.0  
**Last Updated:** 2024-03-27
