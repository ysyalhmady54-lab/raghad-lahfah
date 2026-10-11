from __future__ import annotations

import hashlib
import hmac
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Boolean, DateTime, Integer, String, Text, create_engine, select, update, delete, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "").strip()
SESSION_SECRET = os.getenv("SESSION_SECRET", "").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./raghad_messages.db").strip()

if not ADMIN_PASSWORD or ADMIN_PASSWORD == "CHANGE_THIS_TO_A_LONG_PRIVATE_PASSWORD":
    raise RuntimeError("Set a private ADMIN_PASSWORD in .env or your hosting environment before starting the app.")
if len(ADMIN_PASSWORD) < 12:
    raise RuntimeError("ADMIN_PASSWORD must be at least 12 characters long.")
if not SESSION_SECRET or SESSION_SECRET == "CHANGE_THIS_TO_A_RANDOM_SECRET":
    raise RuntimeError("Set a private SESSION_SECRET in .env or your hosting environment before starting the app.")
if len(SESSION_SECRET) < 32:
    raise RuntimeError("SESSION_SECRET must contain at least 32 characters.")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://") and "+psycopg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

engine_kwargs = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    mood: Mapped[str] = mapped_column(String(32), nullable=False, default="رسالة من القلب")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


Base.metadata.create_all(bind=engine)

app = FastAPI(title="مساحة رغد للرسائل المجهولة", docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
        "img-src 'self' data:; connect-src 'self'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com"
    )
    return response


app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

SESSION_COOKIE = "raghad_inbox_session"
SESSION_TTL = 60 * 60 * 12
# In-memory throttling only: raw IPs are not saved to the messages database.
RATE_LIMIT: dict[str, deque[float]] = defaultdict(deque)
RATE_WINDOW_SECONDS = 60 * 60
RATE_MAX_MESSAGES = 5
ALLOWED_MOODS = {"رسالة من القلب", "اعتراف", "اشتياق ولهفة", "كلمة حلوة", "عتاب بلطف", "شيء لم أقله"}


class NewMessage(BaseModel):
    body: str = Field(min_length=2, max_length=1200)
    mood: str = Field(default="رسالة من القلب", max_length=32)

    @field_validator("body")
    @classmethod
    def validate_body(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("اكتب رسالتك أولًا.")
        if not value:
            raise ValueError("اكتب رسالتك أولًا.")
        return value

    @field_validator("mood")
    @classmethod
    def validate_mood(cls, value: str) -> str:
        return value if value in ALLOWED_MOODS else "رسالة من القلب"


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)


def _sign_expiry(expiry: int) -> str:
    payload = str(expiry)
    signature = hmac.new(SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def _valid_session(token: Optional[str]) -> bool:
    if not token or "." not in token:
        return False
    expiry_text, signature = token.rsplit(".", 1)
    try:
        expiry = int(expiry_text)
    except ValueError:
        return False
    if expiry < int(time.time()):
        return False
    expected = hmac.new(SESSION_SECRET.encode(), expiry_text.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)


def require_admin(request: Request) -> None:
    if not _valid_session(request.cookies.get(SESSION_COOKIE)):
        raise HTTPException(status_code=401, detail="سجّل الدخول لعرض الرسائل.")


def check_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    host = request.headers.get("host")
    if origin and host:
        parsed = urlparse(origin)
        if parsed.netloc != host:
            raise HTTPException(status_code=403, detail="الطلب غير مسموح.")


def _client_key(request: Request) -> str:
    # Use a one-way hash for the transient rate-limit key; never persist the IP.
    address = request.client.host if request.client else "unknown"
    return hmac.new(SESSION_SECRET.encode(), address.encode(), hashlib.sha256).hexdigest()


def _check_rate_limit(request: Request) -> None:
    key = _client_key(request)
    now = time.time()
    queue = RATE_LIMIT[key]
    while queue and now - queue[0] > RATE_WINDOW_SECONDS:
        queue.popleft()
    if len(queue) >= RATE_MAX_MESSAGES:
        raise HTTPException(status_code=429, detail="وصلت رسائل كثيرة من هذا الاتصال. حاول لاحقًا.")
    queue.append(now)
    # Avoid unbounded in-memory growth in a simple single-instance deployment.
    if len(RATE_LIMIT) > 5000:
        for old_key in list(RATE_LIMIT.keys())[:1000]:
            RATE_LIMIT.pop(old_key, None)


@app.get("/", include_in_schema=False)
def home() -> RedirectResponse:
    return RedirectResponse(url="/raghad", status_code=307)


@app.get("/raghad", include_in_schema=False)
def raghad_page() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/inbox", include_in_schema=False)
def inbox_page() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "inbox.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/messages", status_code=201)
def create_message(payload: NewMessage, request: Request) -> dict[str, str]:
    check_same_origin(request)
    _check_rate_limit(request)
    with SessionLocal() as db:
        message = Message(body=payload.body, mood=payload.mood)
        db.add(message)
        db.commit()
    return {"ok": "true", "message": "وصلت رسالتك بأمان. شكرًا لأنك شاركت ما في قلبك 🤍"}


@app.post("/api/login")
def login(payload: LoginRequest, request: Request, response: Response) -> dict[str, str]:
    check_same_origin(request)
    if not hmac.compare_digest(payload.password.encode(), ADMIN_PASSWORD.encode()):
        # A brief delay helps make repeated password guessing less convenient.
        time.sleep(0.4)
        raise HTTPException(status_code=401, detail="كلمة المرور غير صحيحة.")
    expiry = int(time.time()) + SESSION_TTL
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").lower() == "https"
    response.set_cookie(
        key=SESSION_COOKIE,
        value=_sign_expiry(expiry),
        max_age=SESSION_TTL,
        httponly=True,
        secure=secure,
        samesite="strict",
        path="/",
    )
    return {"ok": "true", "message": "تم تسجيل الدخول."}


@app.post("/api/logout")
def logout(request: Request, response: Response) -> dict[str, str]:
    check_same_origin(request)
    response.delete_cookie(key=SESSION_COOKIE, path="/", httponly=True, samesite="strict")
    return {"ok": "true", "message": "تم تسجيل الخروج."}


@app.get("/api/messages")
def list_messages(request: Request, unread_only: bool = False) -> dict[str, object]:
    require_admin(request)
    with SessionLocal() as db:
        query = select(Message).order_by(Message.created_at.desc()).limit(300)
        if unread_only:
            query = select(Message).where(Message.is_read.is_(False)).order_by(Message.created_at.desc()).limit(300)
        rows = db.scalars(query).all()
        total = db.scalar(select(func.count(Message.id))) or 0
        unread = db.scalar(select(func.count(Message.id)).where(Message.is_read.is_(False))) or 0
        messages = [
            {
                "id": row.id,
                "body": row.body,
                "mood": row.mood,
                "created_at": row.created_at.isoformat() if row.created_at else "",
                "is_read": row.is_read,
            }
            for row in rows
        ]
    return {"messages": messages, "total": total, "unread": unread}


@app.patch("/api/messages/{message_id}/read")
def mark_read(message_id: int, request: Request) -> dict[str, str]:
    require_admin(request)
    with SessionLocal() as db:
        result = db.execute(update(Message).where(Message.id == message_id).values(is_read=True))
        db.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="الرسالة غير موجودة.")
    return {"ok": "true"}


@app.delete("/api/messages/{message_id}")
def delete_message(message_id: int, request: Request) -> dict[str, str]:
    require_admin(request)
    with SessionLocal() as db:
        result = db.execute(delete(Message).where(Message.id == message_id))
        db.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="الرسالة غير موجودة.")
    return {"ok": "true"}
