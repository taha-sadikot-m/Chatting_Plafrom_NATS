"""
Database models for the Chat Platform.
Defines User, Message, and ChatSession data structures.
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Index, func, Text

db = SQLAlchemy()


class User(db.Model):
    """Represents a user in the chat platform."""
    
    __tablename__ = "users"
    __table_args__ = (
        Index("idx_user_cognito_id", "cognito_id"),
        Index("idx_user_email", "email"),
        Index("idx_user_active", "is_active"),
    )
    
    id = db.Column(db.String(36), primary_key=True, doc="UUID primary key")
    cognito_id = db.Column(db.String(255), unique=True, nullable=False, doc="AWS Cognito user ID (sub)")
    email = db.Column(db.String(255), unique=True, nullable=False, doc="User email")
    name = db.Column(db.String(255), nullable=False, doc="User display name")
    avatar_color = db.Column(db.String(7), default="#3498db", doc="User avatar background color")
    bio = db.Column(Text, nullable=True, doc="User bio/status")
    is_active = db.Column(db.Boolean, default=True, doc="User active status")
    is_online = db.Column(db.Boolean, default=False, doc="User online status")
    last_seen = db.Column(db.DateTime, default=datetime.utcnow, doc="Last activity time")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, doc="Account creation time")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, doc="Last update time")
    
    # Relationships
    sent_messages = db.relationship(
        "Message",
        foreign_keys="Message.sender_id",
        backref="sender",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )
    chat_sessions = db.relationship(
        "ChatSession",
        secondary="chat_session_participants",
        backref=db.backref("participants", lazy="dynamic"),
        lazy="dynamic"
    )
    
    def to_dict(self, include_email=True, include_status=True):
        """Convert user to dictionary representation."""
        data = {
            "id": self.id,
            "name": self.name,
            "avatar_color": self.avatar_color,
            "is_online": self.is_online,
        }
        if include_email:
            data["email"] = self.email
        if include_status:
            data["bio"] = self.bio
            data["last_seen"] = self.last_seen.isoformat() if self.last_seen else None
        return data
    
    def to_dict_full(self):
        """Get full user information."""
        return {
            "id": self.id,
            "cognito_id": self.cognito_id,
            "email": self.email,
            "name": self.name,
            "avatar_color": self.avatar_color,
            "bio": self.bio,
            "is_active": self.is_active,
            "is_online": self.is_online,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class ChatSession(db.Model):
    """Represents a one-on-one chat session between two users."""
    
    __tablename__ = "chat_sessions"
    __table_args__ = (
        Index("idx_chat_session_created", "created_at"),
        Index("idx_chat_session_updated", "updated_at"),
    )
    
    id = db.Column(db.String(36), primary_key=True, doc="UUID primary key")
    initiator_id = db.Column(
        db.String(36),
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        doc="User who initiated the chat"
    )
    recipient_id = db.Column(
        db.String(36),
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        doc="Other participant in the chat"
    )
    last_message_at = db.Column(db.DateTime, nullable=True, doc="Timestamp of last message")
    is_archived = db.Column(db.Boolean, default=False, doc="Whether session is archived")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, doc="Session creation time")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, doc="Last update time")
    
    # Relationships
    messages = db.relationship(
        "Message",
        foreign_keys="Message.session_id",
        backref="session",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )
    initiator = db.relationship(
        "User",
        foreign_keys=[initiator_id],
        backref="initiated_chats"
    )
    recipient = db.relationship(
        "User",
        foreign_keys=[recipient_id],
        backref="received_chats"
    )
    
    def get_other_user(self, current_user_id):
        """Get the other participant in the chat session."""
        return self.recipient_id if self.initiator_id == current_user_id else self.initiator_id
    
    def to_dict(self):
        """Convert session to dictionary representation."""
        other_id = self.get_other_user(self.initiator_id)
        other_user = User.query.get(other_id)
        return {
            "id": self.id,
            "other_user": other_user.to_dict() if other_user else None,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
            "is_archived": self.is_archived,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class Message(db.Model):
    """Represents a message in a chat session."""
    
    __tablename__ = "messages"
    __table_args__ = (
        Index("idx_message_session", "session_id"),
        Index("idx_message_sender", "sender_id"),
        Index("idx_message_created", "created_at"),
    )
    
    id = db.Column(db.String(36), primary_key=True, doc="UUID primary key")
    session_id = db.Column(
        db.String(36),
        db.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        doc="Chat session ID"
    )
    sender_id = db.Column(
        db.String(36),
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        doc="Sender user ID"
    )
    content = db.Column(Text, nullable=False, doc="Message content/text")
    message_type = db.Column(
        db.String(20),
        default="text",
        doc="Type of message: text, image, file, etc."
    )
    is_edited = db.Column(db.Boolean, default=False, doc="Whether message has been edited")
    edited_at = db.Column(db.DateTime, nullable=True, doc="When message was last edited")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, doc="Message creation time")
    
    def to_dict(self):
        """Convert message to dictionary representation."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "sender": self.sender.to_dict() if self.sender else None,
            "content": self.content,
            "message_type": self.message_type,
            "is_edited": self.is_edited,
            "edited_at": self.edited_at.isoformat() if self.edited_at else None,
            "created_at": self.created_at.isoformat(),
        }


# Association table for many-to-many relationship
chat_participants = db.Table(
    "chat_session_participants",
    db.Column("user_id", db.String(36), db.ForeignKey("users.id", ondelete="CASCADE")),
    db.Column("chat_session_id", db.String(36), db.ForeignKey("chat_sessions.id", ondelete="CASCADE")),
    Index("idx_participants_user", "user_id"),
    Index("idx_participants_session", "chat_session_id"),
)
