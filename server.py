from fastapi import FastAPI, APIRouter, HTTPException, Request, Cookie, Response, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
import httpx
import razorpay
import hmac
import hashlib
import requests as sync_requests
import base64
import secrets

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Razorpay setup
RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID', '')
RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET', '')
razorpay_client = None
if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:
    razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# Stripe setup
STRIPE_API_KEY = os.environ.get('STRIPE_API_KEY', '')

# Create the main app
app = FastAPI(title="VigyaanKart API", version="1.0.0")

# Create routers
api_router = APIRouter(prefix="/api")
auth_router = APIRouter(prefix="/auth", tags=["Authentication"])
ebook_router = APIRouter(prefix="/ebooks", tags=["Ebooks"])
order_router = APIRouter(prefix="/orders", tags=["Orders"])
payment_router = APIRouter(prefix="/payments", tags=["Payments"])
admin_router = APIRouter(prefix="/admin", tags=["Admin"])
user_router = APIRouter(prefix="/users", tags=["Users"])
coupon_router = APIRouter(prefix="/coupons", tags=["Coupons"])
blog_router = APIRouter(prefix="/blog", tags=["Blog"])
contact_router = APIRouter(prefix="/contact", tags=["Contact"])
affiliate_router = APIRouter(prefix="/affiliates", tags=["Affiliates"])
chat_router = APIRouter(prefix="/chat", tags=["Chat"])

# ===================== OBJECT STORAGE =====================
STORAGE_URL = "https://integrations.emergentagent.com/objstore/api/v1/storage"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = "vigyaankart"
_storage_key = None

def init_storage():
    global _storage_key
    if _storage_key:
        return _storage_key
    resp = sync_requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key

def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    resp = sync_requests.put(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key, "Content-Type": content_type},
        data=data, timeout=120
    )
    resp.raise_for_status()
    return resp.json()

def get_object(path: str):
    key = init_storage()
    resp = sync_requests.get(
        f"{STORAGE_URL}/objects/{path}",
        headers={"X-Storage-Key": key}, timeout=60
    )
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ===================== MODELS =====================

class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    email: str
    name: str
    picture: Optional[str] = None
    role: str = "user"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class UserSession(BaseModel):
    user_id: str
    session_token: str
    expires_at: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Ebook(BaseModel):
    model_config = ConfigDict(extra="ignore")
    ebook_id: str = Field(default_factory=lambda: f"ebook_{uuid.uuid4().hex[:12]}")
    title: str
    slug: str
    description: str
    short_description: str
    price: float
    original_price: float
    currency: str = "INR"
    cover_image: str
    pdf_url: Optional[str] = None
    category: str
    benefits: List[str] = []
    income_potential: str = ""
    target_audience: str = ""
    what_you_learn: List[str] = []
    is_active: bool = True
    countdown_hours: int = 24
    purchase_link: str = ""
    copies_sold: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class EbookCreate(BaseModel):
    title: str
    slug: str
    description: str
    short_description: str
    price: float
    original_price: float
    currency: str = "INR"
    cover_image: str
    pdf_url: Optional[str] = None
    category: str
    benefits: List[str] = []
    income_potential: str = ""
    target_audience: str = ""
    what_you_learn: List[str] = []
    countdown_hours: int = 24
    purchase_link: str = ""

class Order(BaseModel):
    model_config = ConfigDict(extra="ignore")
    order_id: str = Field(default_factory=lambda: f"order_{uuid.uuid4().hex[:12]}")
    user_id: str
    user_email: str
    user_name: str
    ebook_id: str
    ebook_title: str
    amount: float
    currency: str = "INR"
    status: str = "pending"
    payment_method: str = ""
    payment_id: Optional[str] = None
    download_token: Optional[str] = None
    download_expires_at: Optional[datetime] = None
    invoice_url: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class PaymentTransaction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    transaction_id: str = Field(default_factory=lambda: f"txn_{uuid.uuid4().hex[:12]}")
    order_id: str
    user_id: str
    amount: float
    currency: str
    payment_gateway: str
    gateway_order_id: Optional[str] = None
    gateway_payment_id: Optional[str] = None
    checkout_session_id: Optional[str] = None
    status: str = "initiated"
    payment_status: str = "pending"
    metadata: Dict[str, Any] = {}
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Coupon(BaseModel):
    model_config = ConfigDict(extra="ignore")
    coupon_id: str = Field(default_factory=lambda: f"coupon_{uuid.uuid4().hex[:8]}")
    code: str
    discount_type: str = "percentage"
    discount_value: float
    max_uses: int = 100
    used_count: int = 0
    min_amount: float = 0
    applicable_ebooks: List[str] = []
    is_active: bool = True
    expires_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class AbandonedCart(BaseModel):
    model_config = ConfigDict(extra="ignore")
    cart_id: str = Field(default_factory=lambda: f"cart_{uuid.uuid4().hex[:12]}")
    user_id: Optional[str] = None
    email: Optional[str] = None
    ebook_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class EmailLog(BaseModel):
    model_config = ConfigDict(extra="ignore")
    email_id: str = Field(default_factory=lambda: f"email_{uuid.uuid4().hex[:12]}")
    to_email: str
    subject: str
    body: str
    status: str = "sent"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class BlogPost(BaseModel):
    model_config = ConfigDict(extra="ignore")
    post_id: str = Field(default_factory=lambda: f"post_{uuid.uuid4().hex[:12]}")
    title: str
    slug: str
    excerpt: str = ""
    content: str = ""
    cover_image: str = ""
    author: str = "VigyaanKart Team"
    category: str = "General"
    tags: List[str] = []
    is_published: bool = True
    read_time: int = 5
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ContactMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message_id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:12]}")
    name: str
    email: str
    subject: str = ""
    message: str
    status: str = "new"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class AffiliateProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    affiliate_id: str = Field(default_factory=lambda: f"aff_{uuid.uuid4().hex[:8]}")
    user_id: str
    referral_code: str = Field(default_factory=lambda: uuid.uuid4().hex[:8].upper())
    total_earnings: float = 0
    total_referrals: int = 0
    pending_payout: float = 0
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class AffiliateReferral(BaseModel):
    model_config = ConfigDict(extra="ignore")
    referral_id: str = Field(default_factory=lambda: f"ref_{uuid.uuid4().hex[:12]}")
    affiliate_id: str
    referred_user_id: Optional[str] = None
    referred_email: Optional[str] = None
    order_id: Optional[str] = None
    commission_amount: float = 0
    status: str = "pending"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message_id: str = Field(default_factory=lambda: f"chatmsg_{uuid.uuid4().hex[:12]}")
    session_id: str
    user_id: Optional[str] = None
    role: str
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class VideoTestimonial(BaseModel):
    model_config = ConfigDict(extra="ignore")
    testimonial_id: str = Field(default_factory=lambda: f"vtest_{uuid.uuid4().hex[:8]}")
    name: str
    role: str = ""
    thumbnail: str = ""
    video_url: str = ""
    video_path: str = ""
    embed_url: str = ""
    quote: str = ""
    rating: int = 5
    is_published: bool = True
    order: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Review(BaseModel):
    model_config = ConfigDict(extra="ignore")
    review_id: str = Field(default_factory=lambda: f"rev_{uuid.uuid4().hex[:8]}")
    name: str
    role: str = ""
    image: str = ""
    text: str = ""
    rating: int = 5
    is_published: bool = True
    order: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# ===================== HELPER FUNCTIONS =====================

async def get_current_user(session_token: Optional[str] = Cookie(None), authorization: Optional[str] = None):
    """Get current user from session token (cookie or header)"""
    token = session_token
    if not token and authorization:
        if authorization.startswith("Bearer "):
            token = authorization[7:]
        else:
            token = authorization
    
    if not token:
        return None
    
    session_doc = await db.user_sessions.find_one({"session_token": token}, {"_id": 0})
    if not session_doc:
        return None
    
    expires_at = session_doc.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        return None
    
    user_doc = await db.users.find_one({"user_id": session_doc["user_id"]}, {"_id": 0})
    return user_doc

async def require_auth(request: Request, session_token: Optional[str] = Cookie(None)):
    """Require authentication middleware"""
    auth_header = request.headers.get("Authorization")
    user = await get_current_user(session_token, auth_header)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

async def require_admin(request: Request, session_token: Optional[str] = Cookie(None)):
    """Require admin role"""
    user = await require_auth(request, session_token)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

def generate_download_token():
    """Generate secure download token"""
    return secrets.token_urlsafe(32)

async def send_mock_email(to_email: str, subject: str, body: str):
    """Mock email sending - logs to database"""
    email_log = EmailLog(to_email=to_email, subject=subject, body=body)
    doc = email_log.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.email_logs.insert_one(doc)
    logger.info(f"[MOCK EMAIL] To: {to_email}, Subject: {subject}")
    logger.info(f"[MOCK EMAIL BODY]: {body[:500]}...")
    return True

# ===================== AUTH ROUTES =====================
# REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH

@auth_router.post("/session")
async def exchange_session(request: Request, response: Response):
    """Exchange session_id from Emergent Auth for user data and session token"""
    body = await request.json()
    session_id = body.get("session_id")
    
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")
    
    async with httpx.AsyncClient() as http_client:
        auth_response = await http_client.get(
            "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
            headers={"X-Session-ID": session_id}
        )
        
        if auth_response.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid session")
        
        auth_data = auth_response.json()
    
    user_id = f"user_{uuid.uuid4().hex[:12]}"
    email = auth_data.get("email")
    name = auth_data.get("name")
    picture = auth_data.get("picture")
    session_token = auth_data.get("session_token")
    
    existing_user = await db.users.find_one({"email": email}, {"_id": 0})
    if existing_user:
        user_id = existing_user["user_id"]
        await db.users.update_one(
            {"email": email},
            {"$set": {"name": name, "picture": picture, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
    else:
        user_doc = {
            "user_id": user_id,
            "email": email,
            "name": name,
            "picture": picture,
            "role": "user",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.users.insert_one(user_doc)
    
    session_doc = {
        "user_id": user_id,
        "session_token": session_token,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.user_sessions.delete_many({"user_id": user_id})
    await db.user_sessions.insert_one(session_doc)
    
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=7 * 24 * 60 * 60
    )
    
    user_data = await db.users.find_one({"user_id": user_id}, {"_id": 0})
    return user_data

@auth_router.post("/admin-login")
async def admin_login(request: Request, response: Response):
    """Admin login with email and password"""
    body = await request.json()
    email = body.get("email")
    password = body.get("password")
    
    # Hardcoded admin credentials (in production, use hashed passwords)
    ADMIN_CREDENTIALS = {
        "admin@vigyaankart.com": "Jaikrish@321#",
        "admin": "admin123"
    }
    
    if email not in ADMIN_CREDENTIALS or ADMIN_CREDENTIALS[email] != password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Find or create admin user
    admin_user = await db.users.find_one({"email": email, "role": "admin"}, {"_id": 0})
    
    if not admin_user:
        user_id = f"admin_{uuid.uuid4().hex[:12]}"
        admin_user = {
            "user_id": user_id,
            "email": email,
            "name": "Admin User",
            "picture": None,
            "role": "admin",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.users.insert_one(admin_user)
    
    # Create session
    session_token = secrets.token_urlsafe(32)
    session_doc = {
        "user_id": admin_user["user_id"],
        "session_token": session_token,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.user_sessions.delete_many({"user_id": admin_user["user_id"]})
    await db.user_sessions.insert_one(session_doc)
    
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
        max_age=7 * 24 * 60 * 60
    )
    
    return {"user": admin_user, "token": session_token}

@auth_router.get("/me")
async def get_me(request: Request, session_token: Optional[str] = Cookie(None)):
    """Get current authenticated user"""
    user = await require_auth(request, session_token)
    return user

@auth_router.post("/logout")
async def logout(response: Response, session_token: Optional[str] = Cookie(None)):
    """Logout user"""
    if session_token:
        await db.user_sessions.delete_many({"session_token": session_token})
    response.delete_cookie(key="session_token", path="/")
    return {"message": "Logged out successfully"}

# ===================== EBOOK ROUTES =====================

@ebook_router.get("/", response_model=List[Dict])
async def get_ebooks(active_only: bool = True):
    """Get all ebooks"""
    query = {"is_active": True} if active_only else {}
    ebooks = await db.ebooks.find(query, {"_id": 0}).to_list(100)
    return ebooks

@ebook_router.get("/{slug}")
async def get_ebook_by_slug(slug: str):
    """Get single ebook by slug"""
    ebook = await db.ebooks.find_one({"slug": slug}, {"_id": 0})
    if not ebook:
        raise HTTPException(status_code=404, detail="Ebook not found")
    return ebook

@ebook_router.get("/id/{ebook_id}")
async def get_ebook_by_id(ebook_id: str):
    """Get single ebook by ID"""
    ebook = await db.ebooks.find_one({"ebook_id": ebook_id}, {"_id": 0})
    if not ebook:
        raise HTTPException(status_code=404, detail="Ebook not found")
    return ebook

@ebook_router.get("/{slug}/related")
async def get_related_ebooks(slug: str):
    """Get related ebooks"""
    ebook = await db.ebooks.find_one({"slug": slug}, {"_id": 0})
    if not ebook:
        raise HTTPException(status_code=404, detail="Ebook not found")
    
    related = await db.ebooks.find(
        {"category": ebook["category"], "slug": {"$ne": slug}, "is_active": True},
        {"_id": 0}
    ).to_list(4)
    return related

# ===================== ORDER ROUTES =====================

@order_router.post("/create")
async def create_order(request: Request, session_token: Optional[str] = Cookie(None)):
    """Create a new order"""
    user = await require_auth(request, session_token)
    body = await request.json()
    
    ebook_id = body.get("ebook_id")
    coupon_code = body.get("coupon_code")
    
    ebook = await db.ebooks.find_one({"ebook_id": ebook_id}, {"_id": 0})
    if not ebook:
        raise HTTPException(status_code=404, detail="Ebook not found")
    
    amount = ebook["price"]
    
    if coupon_code:
        coupon = await db.coupons.find_one({"code": coupon_code.upper(), "is_active": True}, {"_id": 0})
        if coupon:
            if coupon.get("expires_at"):
                expires = datetime.fromisoformat(coupon["expires_at"]) if isinstance(coupon["expires_at"], str) else coupon["expires_at"]
                if expires.tzinfo is None:
                    expires = expires.replace(tzinfo=timezone.utc)
                if expires < datetime.now(timezone.utc):
                    coupon = None
            
            if coupon and coupon.get("used_count", 0) < coupon.get("max_uses", 100):
                if coupon["discount_type"] == "percentage":
                    amount = amount * (1 - coupon["discount_value"] / 100)
                else:
                    amount = max(0, amount - coupon["discount_value"])
    
    order = Order(
        user_id=user["user_id"],
        user_email=user["email"],
        user_name=user["name"],
        ebook_id=ebook_id,
        ebook_title=ebook["title"],
        amount=round(amount, 2),
        currency=ebook.get("currency", "INR")
    )
    
    doc = order.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.orders.insert_one(doc)
    
    return {"order_id": order.order_id, "amount": order.amount, "currency": order.currency}

@order_router.get("/my-orders")
async def get_my_orders(request: Request, session_token: Optional[str] = Cookie(None)):
    """Get current user's orders"""
    user = await require_auth(request, session_token)
    orders = await db.orders.find(
        {"user_id": user["user_id"]},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    return orders

@order_router.get("/my-purchases")
async def get_my_purchases(request: Request, session_token: Optional[str] = Cookie(None)):
    """Get purchased ebooks with download links"""
    user = await require_auth(request, session_token)
    orders = await db.orders.find(
        {"user_id": user["user_id"], "status": "completed"},
        {"_id": 0}
    ).to_list(100)
    
    purchases = []
    for order in orders:
        ebook = await db.ebooks.find_one({"ebook_id": order["ebook_id"]}, {"_id": 0})
        if ebook:
            purchases.append({
                "order": order,
                "ebook": ebook
            })
    
    return purchases

@order_router.get("/{order_id}")
async def get_order(order_id: str, request: Request, session_token: Optional[str] = Cookie(None)):
    """Get order by ID"""
    user = await require_auth(request, session_token)
    order = await db.orders.find_one(
        {"order_id": order_id, "user_id": user["user_id"]},
        {"_id": 0}
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

# ===================== PAYMENT ROUTES =====================

@payment_router.post("/razorpay/create-order")
async def create_razorpay_order(request: Request, session_token: Optional[str] = Cookie(None)):
    """Create Razorpay order"""
    user = await require_auth(request, session_token)
    body = await request.json()
    order_id = body.get("order_id")
    
    if not razorpay_client:
        raise HTTPException(status_code=503, detail="Razorpay not configured")
    
    order = await db.orders.find_one({"order_id": order_id, "user_id": user["user_id"]}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    amount_paise = int(order["amount"] * 100)
    
    try:
        razor_order = razorpay_client.order.create({
            "amount": amount_paise,
            "currency": order.get("currency", "INR"),
            "receipt": order_id[:40],
            "payment_capture": 1
        })
        
        txn = PaymentTransaction(
            order_id=order_id,
            user_id=user["user_id"],
            amount=order["amount"],
            currency=order.get("currency", "INR"),
            payment_gateway="razorpay",
            gateway_order_id=razor_order["id"],
            status="created",
            payment_status="pending"
        )
        doc = txn.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        doc['updated_at'] = doc['updated_at'].isoformat()
        await db.payment_transactions.insert_one(doc)
        
        await db.orders.update_one(
            {"order_id": order_id},
            {"$set": {"payment_method": "razorpay"}}
        )
        
        return {
            "razorpay_order_id": razor_order["id"],
            "razorpay_key": RAZORPAY_KEY_ID,
            "amount": amount_paise,
            "currency": order.get("currency", "INR"),
            "order_id": order_id
        }
    except Exception as e:
        logger.error(f"Razorpay order creation failed: {e}")
        raise HTTPException(status_code=500, detail="Payment order creation failed")

@payment_router.post("/razorpay/verify")
async def verify_razorpay_payment(request: Request, session_token: Optional[str] = Cookie(None)):
    """Verify Razorpay payment"""
    user = await require_auth(request, session_token)
    body = await request.json()
    
    razorpay_order_id = body.get("razorpay_order_id")
    razorpay_payment_id = body.get("razorpay_payment_id")
    razorpay_signature = body.get("razorpay_signature")
    order_id = body.get("order_id")
    
    if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
        raise HTTPException(status_code=400, detail="Missing payment verification data")
    
    msg = f"{razorpay_order_id}|{razorpay_payment_id}"
    generated_signature = hmac.new(
        RAZORPAY_KEY_SECRET.encode(),
        msg.encode(),
        hashlib.sha256
    ).hexdigest()
    
    if generated_signature != razorpay_signature:
        await db.payment_transactions.update_one(
            {"gateway_order_id": razorpay_order_id},
            {"$set": {"status": "failed", "payment_status": "failed", "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        raise HTTPException(status_code=400, detail="Payment verification failed")
    
    await db.payment_transactions.update_one(
        {"gateway_order_id": razorpay_order_id},
        {"$set": {
            "gateway_payment_id": razorpay_payment_id,
            "status": "completed",
            "payment_status": "paid",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    download_token = generate_download_token()
    download_expires = datetime.now(timezone.utc) + timedelta(hours=48)
    
    await db.orders.update_one(
        {"order_id": order_id},
        {"$set": {
            "status": "completed",
            "payment_id": razorpay_payment_id,
            "download_token": download_token,
            "download_expires_at": download_expires.isoformat()
        }}
    )
    
    order = await db.orders.find_one({"order_id": order_id}, {"_id": 0})
    ebook = await db.ebooks.find_one({"ebook_id": order["ebook_id"]}, {"_id": 0})
    
    await db.ebooks.update_one(
        {"ebook_id": order["ebook_id"]},
        {"$inc": {"copies_sold": 1}}
    )
    
    await send_mock_email(
        to_email=order["user_email"],
        subject=f"Your VigyaanKart Purchase: {ebook['title']}",
        body=f"""
Dear {order['user_name']},

Thank you for your purchase of "{ebook['title']}"!

Your download link (valid for 48 hours):
Download Token: {download_token}

Order Details:
- Order ID: {order_id}
- Amount: ₹{order['amount']}
- Payment ID: {razorpay_payment_id}

You can also access your purchase from your dashboard.

Happy Learning!
Team VigyaanKart
        """
    )
    
    return {"success": True, "order_id": order_id, "download_token": download_token}

@payment_router.post("/stripe/create-session")
async def create_stripe_checkout(request: Request, session_token: Optional[str] = Cookie(None)):
    """Create Stripe checkout session"""
    from emergentintegrations.payments.stripe.checkout import StripeCheckout, CheckoutSessionRequest
    
    user = await require_auth(request, session_token)
    body = await request.json()
    order_id = body.get("order_id")
    origin_url = body.get("origin_url")
    
    if not STRIPE_API_KEY:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    
    order = await db.orders.find_one({"order_id": order_id, "user_id": user["user_id"]}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    host_url = str(request.base_url).rstrip('/')
    webhook_url = f"{host_url}/api/webhook/stripe"
    
    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)
    
    success_url = f"{origin_url}/payment/success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin_url}/checkout/{order_id}"
    
    amount_usd = round(order["amount"] / 83, 2)
    
    checkout_request = CheckoutSessionRequest(
        amount=amount_usd,
        currency="usd",
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={
            "order_id": order_id,
            "user_id": user["user_id"],
            "ebook_id": order["ebook_id"]
        }
    )
    
    session = await stripe_checkout.create_checkout_session(checkout_request)
    
    txn = PaymentTransaction(
        order_id=order_id,
        user_id=user["user_id"],
        amount=amount_usd,
        currency="usd",
        payment_gateway="stripe",
        checkout_session_id=session.session_id,
        status="initiated",
        payment_status="pending",
        metadata={"stripe_session_url": session.url}
    )
    doc = txn.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    doc['updated_at'] = doc['updated_at'].isoformat()
    await db.payment_transactions.insert_one(doc)
    
    await db.orders.update_one(
        {"order_id": order_id},
        {"$set": {"payment_method": "stripe"}}
    )
    
    return {"checkout_url": session.url, "session_id": session.session_id}

@payment_router.get("/stripe/status/{session_id}")
async def get_stripe_status(session_id: str, request: Request, session_token: Optional[str] = Cookie(None)):
    """Get Stripe checkout session status"""
    from emergentintegrations.payments.stripe.checkout import StripeCheckout
    
    user = await require_auth(request, session_token)
    
    host_url = str(request.base_url).rstrip('/')
    webhook_url = f"{host_url}/api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)
    
    status = await stripe_checkout.get_checkout_status(session_id)
    
    if status.payment_status == "paid":
        txn = await db.payment_transactions.find_one(
            {"checkout_session_id": session_id},
            {"_id": 0}
        )
        
        if txn and txn.get("payment_status") != "paid":
            await db.payment_transactions.update_one(
                {"checkout_session_id": session_id},
                {"$set": {
                    "status": "completed",
                    "payment_status": "paid",
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            order_id = status.metadata.get("order_id") or txn.get("order_id")
            
            download_token = generate_download_token()
            download_expires = datetime.now(timezone.utc) + timedelta(hours=48)
            
            await db.orders.update_one(
                {"order_id": order_id},
                {"$set": {
                    "status": "completed",
                    "payment_id": session_id,
                    "download_token": download_token,
                    "download_expires_at": download_expires.isoformat()
                }}
            )
            
            order = await db.orders.find_one({"order_id": order_id}, {"_id": 0})
            if order:
                ebook = await db.ebooks.find_one({"ebook_id": order["ebook_id"]}, {"_id": 0})
                
                await db.ebooks.update_one(
                    {"ebook_id": order["ebook_id"]},
                    {"$inc": {"copies_sold": 1}}
                )
                
                await send_mock_email(
                    to_email=order["user_email"],
                    subject=f"Your VigyaanKart Purchase: {ebook['title']}",
                    body=f"""
Dear {order['user_name']},

Thank you for your purchase of "{ebook['title']}"!

Your download link (valid for 48 hours):
Download Token: {download_token}

Order Details:
- Order ID: {order_id}
- Amount: ${txn['amount']} USD

You can also access your purchase from your dashboard.

Happy Learning!
Team VigyaanKart
                    """
                )
    
    return {
        "status": status.status,
        "payment_status": status.payment_status,
        "amount_total": status.amount_total,
        "currency": status.currency
    }

@api_router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    """Handle Stripe webhooks"""
    from emergentintegrations.payments.stripe.checkout import StripeCheckout
    
    body = await request.body()
    signature = request.headers.get("Stripe-Signature", "")
    
    host_url = str(request.base_url).rstrip('/')
    webhook_url = f"{host_url}/api/webhook/stripe"
    stripe_checkout = StripeCheckout(api_key=STRIPE_API_KEY, webhook_url=webhook_url)
    
    try:
        webhook_response = await stripe_checkout.handle_webhook(body, signature)
        
        if webhook_response.payment_status == "paid":
            await db.payment_transactions.update_one(
                {"checkout_session_id": webhook_response.session_id},
                {"$set": {
                    "status": "completed",
                    "payment_status": "paid",
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
        
        return {"status": "processed"}
    except Exception as e:
        logger.error(f"Stripe webhook error: {e}")
        return {"status": "error"}

# ===================== DOWNLOAD ROUTES =====================

@api_router.get("/download/{order_id}")
async def download_ebook(order_id: str, token: str, request: Request, session_token: Optional[str] = Cookie(None)):
    """Get download URL for purchased ebook"""
    user = await require_auth(request, session_token)
    
    order = await db.orders.find_one(
        {"order_id": order_id, "user_id": user["user_id"], "status": "completed"},
        {"_id": 0}
    )
    
    if not order:
        raise HTTPException(status_code=404, detail="Order not found or not completed")
    
    if order.get("download_token") != token:
        raise HTTPException(status_code=403, detail="Invalid download token")
    
    expires_at = order.get("download_expires_at")
    if expires_at:
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=403, detail="Download link expired")
    
    ebook = await db.ebooks.find_one({"ebook_id": order["ebook_id"]}, {"_id": 0})
    if not ebook or not ebook.get("pdf_url"):
        raise HTTPException(status_code=404, detail="Ebook file not found")
    
    return {"download_url": ebook["pdf_url"], "title": ebook["title"]}

# ===================== COUPON ROUTES =====================

@coupon_router.post("/validate")
async def validate_coupon(request: Request):
    """Validate coupon code"""
    body = await request.json()
    code = body.get("code", "").upper()
    amount = body.get("amount", 0)
    
    coupon = await db.coupons.find_one({"code": code, "is_active": True}, {"_id": 0})
    if not coupon:
        raise HTTPException(status_code=404, detail="Invalid coupon code")
    
    if coupon.get("expires_at"):
        expires = datetime.fromisoformat(coupon["expires_at"]) if isinstance(coupon["expires_at"], str) else coupon["expires_at"]
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Coupon has expired")
    
    if coupon.get("used_count", 0) >= coupon.get("max_uses", 100):
        raise HTTPException(status_code=400, detail="Coupon usage limit reached")
    
    if amount < coupon.get("min_amount", 0):
        raise HTTPException(status_code=400, detail=f"Minimum order amount is ₹{coupon['min_amount']}")
    
    if coupon["discount_type"] == "percentage":
        discount = amount * (coupon["discount_value"] / 100)
    else:
        discount = min(coupon["discount_value"], amount)
    
    return {
        "valid": True,
        "discount_type": coupon["discount_type"],
        "discount_value": coupon["discount_value"],
        "discount_amount": round(discount, 2),
        "final_amount": round(amount - discount, 2)
    }

# ===================== ADMIN ROUTES =====================

@admin_router.get("/dashboard")
async def admin_dashboard(request: Request, session_token: Optional[str] = Cookie(None)):
    """Get admin dashboard overview"""
    await require_admin(request, session_token)
    
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)
    month_start = today_start.replace(day=1)
    year_start = today_start.replace(month=1, day=1)
    
    total_orders = await db.orders.count_documents({"status": "completed"})
    total_revenue_cursor = db.orders.aggregate([
        {"$match": {"status": "completed"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ])
    total_revenue_list = await total_revenue_cursor.to_list(1)
    total_revenue = total_revenue_list[0]["total"] if total_revenue_list else 0
    
    daily_revenue_cursor = db.orders.aggregate([
        {"$match": {"status": "completed", "created_at": {"$gte": today_start.isoformat()}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ])
    daily_revenue_list = await daily_revenue_cursor.to_list(1)
    daily_revenue = daily_revenue_list[0]["total"] if daily_revenue_list else 0
    
    monthly_revenue_cursor = db.orders.aggregate([
        {"$match": {"status": "completed", "created_at": {"$gte": month_start.isoformat()}}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
    ])
    monthly_revenue_list = await monthly_revenue_cursor.to_list(1)
    monthly_revenue = monthly_revenue_list[0]["total"] if monthly_revenue_list else 0
    
    total_users = await db.users.count_documents({})
    total_ebooks = await db.ebooks.count_documents({})
    
    ebook_stats_cursor = db.orders.aggregate([
        {"$match": {"status": "completed"}},
        {"$group": {
            "_id": "$ebook_id",
            "ebook_title": {"$first": "$ebook_title"},
            "copies_sold": {"$sum": 1},
            "revenue": {"$sum": "$amount"}
        }},
        {"$sort": {"revenue": -1}},
        {"$limit": 10}
    ])
    ebook_stats = await ebook_stats_cursor.to_list(10)
    
    failed_payments = await db.payment_transactions.count_documents({"status": "failed"})
    successful_payments = await db.payment_transactions.count_documents({"status": "completed"})
    
    # Affiliate metrics
    total_affiliates = await db.affiliates.count_documents({})
    aff_commission_cursor = db.affiliates.aggregate([
        {"$group": {"_id": None, "total": {"$sum": "$total_earnings"}}}
    ])
    aff_commission_list = await aff_commission_cursor.to_list(1)
    total_affiliate_commission = aff_commission_list[0]["total"] if aff_commission_list else 0
    
    return {
        "overview": {
            "total_revenue": round(total_revenue, 2),
            "daily_revenue": round(daily_revenue, 2),
            "monthly_revenue": round(monthly_revenue, 2),
            "total_orders": total_orders,
            "total_users": total_users,
            "total_ebooks": total_ebooks
        },
        "payment_stats": {
            "successful": successful_payments,
            "failed": failed_payments,
            "success_rate": round(successful_payments / max(successful_payments + failed_payments, 1) * 100, 2)
        },
        "affiliate_stats": {
            "total_affiliates": total_affiliates,
            "total_commission": round(total_affiliate_commission, 2)
        },
        "top_ebooks": ebook_stats
    }

@admin_router.get("/analytics/revenue")
async def get_revenue_analytics(
    request: Request,
    session_token: Optional[str] = Cookie(None),
    period: str = Query("monthly", enum=["daily", "weekly", "monthly", "yearly"])
):
    """Get revenue analytics"""
    await require_admin(request, session_token)
    
    now = datetime.now(timezone.utc)
    
    if period == "daily":
        start_date = now - timedelta(days=30)
        group_format = "%Y-%m-%d"
    elif period == "weekly":
        start_date = now - timedelta(weeks=12)
        group_format = "%Y-W%V"
    elif period == "monthly":
        start_date = now - timedelta(days=365)
        group_format = "%Y-%m"
    else:
        start_date = now - timedelta(days=365*3)
        group_format = "%Y"
    
    pipeline = [
        {"$match": {"status": "completed", "created_at": {"$gte": start_date.isoformat()}}},
        {"$addFields": {
            "date": {"$dateFromString": {"dateString": "$created_at"}}
        }},
        {"$group": {
            "_id": {"$dateToString": {"format": group_format, "date": "$date"}},
            "revenue": {"$sum": "$amount"},
            "orders": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]
    
    results = await db.orders.aggregate(pipeline).to_list(100)
    return results

@admin_router.get("/ebooks")
async def admin_get_ebooks(request: Request, session_token: Optional[str] = Cookie(None)):
    """Get all ebooks for admin"""
    await require_admin(request, session_token)
    ebooks = await db.ebooks.find({}, {"_id": 0}).to_list(100)
    return ebooks

@admin_router.post("/ebooks")
async def admin_create_ebook(request: Request, session_token: Optional[str] = Cookie(None)):
    """Create new ebook"""
    await require_admin(request, session_token)
    body = await request.json()
    
    ebook_data = EbookCreate(**body)
    ebook = Ebook(**ebook_data.model_dump())
    
    doc = ebook.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    doc['updated_at'] = doc['updated_at'].isoformat()
    await db.ebooks.insert_one(doc)
    
    return {"ebook_id": ebook.ebook_id, "message": "Ebook created successfully"}

@admin_router.put("/ebooks/{ebook_id}")
async def admin_update_ebook(ebook_id: str, request: Request, session_token: Optional[str] = Cookie(None)):
    """Update ebook"""
    await require_admin(request, session_token)
    body = await request.json()
    
    body["updated_at"] = datetime.now(timezone.utc).isoformat()
    body.pop("ebook_id", None)
    body.pop("created_at", None)
    
    result = await db.ebooks.update_one(
        {"ebook_id": ebook_id},
        {"$set": body}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Ebook not found")
    
    return {"message": "Ebook updated successfully"}

# File upload for ebook PDF
@admin_router.post("/upload/pdf")
async def admin_upload_pdf(request: Request, file: UploadFile = File(...), session_token: Optional[str] = Cookie(None)):
    """Upload a PDF file for an ebook"""
    await require_admin(request, session_token)
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    data = await file.read()
    if len(data) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 50MB)")
    ext = "pdf"
    path = f"{APP_NAME}/ebooks/{uuid.uuid4()}.{ext}"
    result = put_object(path, data, "application/pdf")
    await db.files.insert_one({
        "file_id": f"file_{uuid.uuid4().hex[:12]}",
        "storage_path": result["path"],
        "original_filename": file.filename,
        "content_type": "application/pdf",
        "size": result.get("size", len(data)),
        "type": "ebook_pdf",
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    return {"path": result["path"], "filename": file.filename, "size": len(data)}

# File upload for images (blog covers, etc.)
@admin_router.post("/upload/image")
async def admin_upload_image(request: Request, file: UploadFile = File(...), session_token: Optional[str] = Cookie(None)):
    """Upload an image file"""
    await require_admin(request, session_token)
    allowed = ('.jpg', '.jpeg', '.png', '.webp', '.gif')
    if not any(file.filename.lower().endswith(ext) for ext in allowed):
        raise HTTPException(status_code=400, detail="Only JPG, PNG, WebP, GIF images are allowed")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")
    ext = file.filename.split(".")[-1].lower()
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp", "gif": "image/gif"}
    path = f"{APP_NAME}/images/{uuid.uuid4()}.{ext}"
    result = put_object(path, data, mime_map.get(ext, "image/jpeg"))
    await db.files.insert_one({
        "file_id": f"file_{uuid.uuid4().hex[:12]}",
        "storage_path": result["path"],
        "original_filename": file.filename,
        "content_type": mime_map.get(ext, "image/jpeg"),
        "size": result.get("size", len(data)),
        "type": "image",
        "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    return {"path": result["path"], "filename": file.filename, "size": len(data)}

# Serve uploaded files
@api_router.get("/files/{path:path}")
async def serve_file(path: str):
    """Serve an uploaded file from storage"""
    try:
        data, content_type = get_object(path)
        return Response(content=data, media_type=content_type)
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")

@admin_router.delete("/ebooks/{ebook_id}")
async def admin_delete_ebook(ebook_id: str, request: Request, session_token: Optional[str] = Cookie(None)):
    """Delete/disable ebook"""
    await require_admin(request, session_token)
    
    result = await db.ebooks.update_one(
        {"ebook_id": ebook_id},
        {"$set": {"is_active": False, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Ebook not found")
    
    return {"message": "Ebook disabled successfully"}

@admin_router.get("/customers")
async def admin_get_customers(
    request: Request,
    session_token: Optional[str] = Cookie(None),
    ebook_id: Optional[str] = None
):
    """Get all customers"""
    await require_admin(request, session_token)
    
    query = {}
    if ebook_id:
        order_user_ids = await db.orders.distinct("user_id", {"ebook_id": ebook_id, "status": "completed"})
        query = {"user_id": {"$in": order_user_ids}}
    
    users = await db.users.find(query, {"_id": 0}).to_list(1000)
    
    for user in users:
        user["orders_count"] = await db.orders.count_documents({"user_id": user["user_id"], "status": "completed"})
        total_spent_cursor = db.orders.aggregate([
            {"$match": {"user_id": user["user_id"], "status": "completed"}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ])
        total_spent_list = await total_spent_cursor.to_list(1)
        user["total_spent"] = total_spent_list[0]["total"] if total_spent_list else 0
    
    return users

@admin_router.get("/failed-payments")
async def admin_get_failed_payments(request: Request, session_token: Optional[str] = Cookie(None)):
    """Get failed payments"""
    await require_admin(request, session_token)
    
    payments = await db.payment_transactions.find(
        {"status": "failed"},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    
    return payments

@admin_router.get("/all-payments")
async def admin_get_all_payments(request: Request, session_token: Optional[str] = Cookie(None), status: Optional[str] = None):
    """Get all payments with customer details"""
    await require_admin(request, session_token)
    query = {}
    if status:
        query["status"] = status
    
    orders = await db.orders.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    enriched = []
    for order in orders:
        user = await db.users.find_one({"user_id": order.get("user_id")}, {"_id": 0, "name": 1, "email": 1, "phone": 1})
        enriched.append({
            "order_id": order.get("order_id"),
            "customer_name": user.get("name", "N/A") if user else order.get("user_name", "N/A"),
            "email": user.get("email", "N/A") if user else order.get("user_email", "N/A"),
            "phone": user.get("phone", "N/A") if user else "N/A",
            "ebook_title": order.get("ebook_title", "N/A"),
            "amount": order.get("amount", 0),
            "status": order.get("status", "pending"),
            "payment_gateway": order.get("payment_gateway", "N/A"),
            "created_at": order.get("created_at", ""),
        })
    return enriched

@admin_router.get("/ebook-sales-analytics")
async def admin_ebook_sales_analytics(request: Request, session_token: Optional[str] = Cookie(None)):
    """Get ebook-wise sales analytics (daily, monthly, total)"""
    await require_admin(request, session_token)
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    ebooks = await db.ebooks.find({}, {"_id": 0, "ebook_id": 1, "title": 1, "cover_image": 1, "price": 1}).to_list(50)
    analytics = []
    for ebook in ebooks:
        eid = ebook["ebook_id"]
        total_sales = await db.orders.count_documents({"ebook_id": eid, "status": "completed"})
        daily_sales = await db.orders.count_documents({"ebook_id": eid, "status": "completed", "created_at": {"$gte": today_start}})
        monthly_sales = await db.orders.count_documents({"ebook_id": eid, "status": "completed", "created_at": {"$gte": month_start}})
        
        rev_cursor = db.orders.aggregate([
            {"$match": {"ebook_id": eid, "status": "completed"}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ])
        rev_list = await rev_cursor.to_list(1)
        total_revenue = rev_list[0]["total"] if rev_list else 0
        
        daily_rev_cursor = db.orders.aggregate([
            {"$match": {"ebook_id": eid, "status": "completed", "created_at": {"$gte": today_start}}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ])
        daily_rev_list = await daily_rev_cursor.to_list(1)
        daily_revenue = daily_rev_list[0]["total"] if daily_rev_list else 0
        
        monthly_rev_cursor = db.orders.aggregate([
            {"$match": {"ebook_id": eid, "status": "completed", "created_at": {"$gte": month_start}}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}}
        ])
        monthly_rev_list = await monthly_rev_cursor.to_list(1)
        monthly_revenue = monthly_rev_list[0]["total"] if monthly_rev_list else 0
        
        analytics.append({
            "ebook_id": eid,
            "title": ebook["title"],
            "cover_image": ebook.get("cover_image", ""),
            "price": ebook.get("price", 0),
            "daily_sales": daily_sales,
            "monthly_sales": monthly_sales,
            "total_sales": total_sales,
            "daily_revenue": round(daily_revenue, 2),
            "monthly_revenue": round(monthly_revenue, 2),
            "total_revenue": round(total_revenue, 2),
        })
    
    return analytics

@admin_router.get("/coupons")
async def admin_get_coupons(request: Request, session_token: Optional[str] = Cookie(None)):
    """Get all coupons"""
    await require_admin(request, session_token)
    coupons = await db.coupons.find({}, {"_id": 0}).to_list(100)
    return coupons

@admin_router.post("/coupons")
async def admin_create_coupon(request: Request, session_token: Optional[str] = Cookie(None)):
    """Create new coupon"""
    await require_admin(request, session_token)
    body = await request.json()
    
    coupon = Coupon(
        code=body["code"].upper(),
        discount_type=body.get("discount_type", "percentage"),
        discount_value=body["discount_value"],
        max_uses=body.get("max_uses", 100),
        min_amount=body.get("min_amount", 0),
        applicable_ebooks=body.get("applicable_ebooks", []),
        expires_at=body.get("expires_at")
    )
    
    doc = coupon.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    if doc.get('expires_at') and isinstance(doc['expires_at'], datetime):
        doc['expires_at'] = doc['expires_at'].isoformat()
    
    await db.coupons.insert_one(doc)
    
    return {"coupon_id": coupon.coupon_id, "message": "Coupon created successfully"}

@admin_router.get("/email-logs")
async def admin_get_email_logs(request: Request, session_token: Optional[str] = Cookie(None)):
    """Get email logs (mock emails)"""
    await require_admin(request, session_token)
    logs = await db.email_logs.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return logs

# ===================== USER ROUTES =====================

@user_router.get("/profile")
async def get_user_profile(request: Request, session_token: Optional[str] = Cookie(None)):
    """Get user profile"""
    user = await require_auth(request, session_token)
    return user

@user_router.put("/profile")
async def update_user_profile(request: Request, session_token: Optional[str] = Cookie(None)):
    """Update user profile"""
    user = await require_auth(request, session_token)
    body = await request.json()
    
    allowed_fields = ["name"]
    update_data = {k: v for k, v in body.items() if k in allowed_fields}
    
    if update_data:
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": update_data}
        )
    
    updated_user = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return updated_user

# ===================== BLOG ROUTES =====================

@blog_router.get("/posts")
async def get_blog_posts(category: Optional[str] = None, limit: int = 20):
    """Get published blog posts"""
    query = {"is_published": True}
    if category:
        query["category"] = category
    posts = await db.blog_posts.find(query, {"_id": 0, "content": 0}).sort("created_at", -1).to_list(limit)
    return posts

@blog_router.get("/posts/{slug}")
async def get_blog_post(slug: str):
    """Get single blog post by slug"""
    post = await db.blog_posts.find_one({"slug": slug, "is_published": True}, {"_id": 0})
    if not post:
        raise HTTPException(status_code=404, detail="Blog post not found")
    return post

@blog_router.get("/categories")
async def get_blog_categories():
    """Get all blog categories"""
    categories = await db.blog_posts.distinct("category", {"is_published": True})
    return categories

# Admin blog management
@admin_router.get("/blog")
async def admin_get_blog_posts(request: Request, session_token: Optional[str] = Cookie(None)):
    """Get all blog posts for admin"""
    await require_admin(request, session_token)
    posts = await db.blog_posts.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return posts

@admin_router.post("/blog")
async def admin_create_blog_post(request: Request, session_token: Optional[str] = Cookie(None)):
    """Create new blog post"""
    await require_admin(request, session_token)
    body = await request.json()
    post = BlogPost(**body)
    doc = post.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    doc['updated_at'] = doc['updated_at'].isoformat()
    await db.blog_posts.insert_one(doc)
    return {"post_id": post.post_id, "message": "Blog post created successfully"}

@admin_router.put("/blog/{post_id}")
async def admin_update_blog_post(post_id: str, request: Request, session_token: Optional[str] = Cookie(None)):
    """Update blog post"""
    await require_admin(request, session_token)
    body = await request.json()
    body["updated_at"] = datetime.now(timezone.utc).isoformat()
    body.pop("post_id", None)
    body.pop("created_at", None)
    result = await db.blog_posts.update_one({"post_id": post_id}, {"$set": body})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Blog post not found")
    return {"message": "Blog post updated successfully"}

@admin_router.delete("/blog/{post_id}")
async def admin_delete_blog_post(post_id: str, request: Request, session_token: Optional[str] = Cookie(None)):
    """Delete blog post"""
    await require_admin(request, session_token)
    result = await db.blog_posts.delete_one({"post_id": post_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Blog post not found")
    return {"message": "Blog post deleted successfully"}

# ===================== CONTACT ROUTES =====================

@contact_router.post("/submit")
async def submit_contact(request: Request):
    """Submit a contact form message"""
    body = await request.json()
    name = body.get("name", "").strip()
    email = body.get("email", "").strip()
    subject = body.get("subject", "").strip()
    message = body.get("message", "").strip()
    if not name or not email or not message:
        raise HTTPException(status_code=400, detail="Name, email, and message are required")
    msg = ContactMessage(name=name, email=email, subject=subject, message=message)
    doc = msg.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.contact_messages.insert_one(doc)
    await send_mock_email(
        to_email="support@vigyaankart.com",
        subject=f"New Contact: {subject or 'No Subject'}",
        body=f"From: {name} ({email})\n\n{message}"
    )
    return {"message": "Your message has been sent successfully. We'll get back to you soon!"}

@admin_router.get("/contact-messages")
async def admin_get_contact_messages(request: Request, session_token: Optional[str] = Cookie(None)):
    """Get contact form messages"""
    await require_admin(request, session_token)
    messages = await db.contact_messages.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return messages

# ===================== AFFILIATE ROUTES =====================

@affiliate_router.post("/join")
async def join_affiliate(request: Request, session_token: Optional[str] = Cookie(None)):
    """Join the affiliate program"""
    user = await require_auth(request, session_token)
    existing = await db.affiliates.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if existing:
        return existing
    profile = AffiliateProfile(user_id=user["user_id"])
    doc = profile.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.affiliates.insert_one(doc)
    return {k: v for k, v in doc.items() if k != '_id'}

@affiliate_router.get("/me")
async def get_my_affiliate(request: Request, session_token: Optional[str] = Cookie(None)):
    """Get current user's affiliate profile"""
    user = await require_auth(request, session_token)
    profile = await db.affiliates.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not profile:
        raise HTTPException(status_code=404, detail="Not an affiliate yet")
    referrals = await db.affiliate_referrals.find({"affiliate_id": profile["affiliate_id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    profile["referrals"] = referrals
    return profile

@affiliate_router.get("/track/{referral_code}")
async def track_referral(referral_code: str, response: Response):
    """Track a referral visit"""
    profile = await db.affiliates.find_one({"referral_code": referral_code, "is_active": True}, {"_id": 0})
    if not profile:
        raise HTTPException(status_code=404, detail="Invalid referral code")
    response.set_cookie(key="ref_code", value=referral_code, max_age=30*24*60*60, path="/")
    return {"message": "Referral tracked", "referral_code": referral_code}

# Admin affiliate management
@admin_router.get("/affiliates")
async def admin_get_affiliates(request: Request, session_token: Optional[str] = Cookie(None)):
    """Get all affiliates"""
    await require_admin(request, session_token)
    affiliates = await db.affiliates.find({}, {"_id": 0}).to_list(200)
    for aff in affiliates:
        user = await db.users.find_one({"user_id": aff["user_id"]}, {"_id": 0})
        aff["user_name"] = user.get("name", "Unknown") if user else "Unknown"
        aff["user_email"] = user.get("email", "") if user else ""
    return affiliates

@admin_router.get("/affiliate-settings")
async def admin_get_affiliate_settings(request: Request, session_token: Optional[str] = Cookie(None)):
    """Get affiliate settings"""
    await require_admin(request, session_token)
    settings = await db.settings.find_one({"key": "affiliate"}, {"_id": 0})
    if not settings:
        settings = {"key": "affiliate", "commission_percent": 10, "min_payout": 500}
    return settings

@admin_router.put("/affiliate-settings")
async def admin_update_affiliate_settings(request: Request, session_token: Optional[str] = Cookie(None)):
    """Update affiliate settings"""
    await require_admin(request, session_token)
    body = await request.json()
    await db.settings.update_one(
        {"key": "affiliate"},
        {"$set": {"commission_percent": body.get("commission_percent", 10), "min_payout": body.get("min_payout", 500)}},
        upsert=True
    )
    return {"message": "Affiliate settings updated"}

# ===================== AI CHAT ROUTES =====================

@chat_router.post("/message")
async def send_chat_message(request: Request, session_token: Optional[str] = Cookie(None)):
    """Send a message to the AI assistant"""
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    body = await request.json()
    user_msg = body.get("message", "")
    chat_session_id = body.get("session_id", f"anon_{uuid.uuid4().hex[:8]}")
    if not user_msg:
        raise HTTPException(status_code=400, detail="Message is required")
    
    user = await get_current_user(session_token, request.headers.get("Authorization"))
    user_id = user["user_id"] if user else None
    
    # Store user message
    user_chat = ChatMessage(session_id=chat_session_id, user_id=user_id, role="user", content=user_msg)
    udoc = user_chat.model_dump()
    udoc['created_at'] = udoc['created_at'].isoformat()
    await db.chat_messages.insert_one(udoc)
    
    # Get conversation history for context
    history = await db.chat_messages.find(
        {"session_id": chat_session_id},
        {"_id": 0, "role": 1, "content": 1}
    ).sort("created_at", 1).to_list(20)
    
    llm_key = os.environ.get("EMERGENT_LLM_KEY", "")
    ebooks = await db.ebooks.find({"is_active": True}, {"_id": 0, "title": 1, "slug": 1, "price": 1, "category": 1, "short_description": 1}).to_list(20)
    ebook_info = "\n".join([f"- {e['title']} (₹{e['price']}) - {e['short_description']}" for e in ebooks])
    
    system_msg = f"""You are VigyaanKart's AI assistant. Help users find the right income blueprint ebook for their goals.
Be friendly, concise, and helpful. If users ask about earning money, careers, or business, recommend relevant ebooks.

Available ebooks:
{ebook_info}

Guidelines:
- Keep responses under 150 words
- Be encouraging and supportive
- Suggest specific ebooks when relevant
- For unrelated questions, politely redirect to income/career topics"""

    chat = LlmChat(api_key=llm_key, session_id=chat_session_id, system_message=system_msg)
    chat.with_model("openai", "gpt-5.2")
    
    # Replay history to maintain context
    for msg in history[:-1]:
        if msg["role"] == "user":
            await chat.send_message(UserMessage(text=msg["content"]))
    
    response_text = await chat.send_message(UserMessage(text=user_msg))
    
    # Store assistant message
    asst_chat = ChatMessage(session_id=chat_session_id, user_id=user_id, role="assistant", content=response_text)
    adoc = asst_chat.model_dump()
    adoc['created_at'] = adoc['created_at'].isoformat()
    await db.chat_messages.insert_one(adoc)
    
    return {"response": response_text, "session_id": chat_session_id}

@chat_router.get("/history/{session_id}")
async def get_chat_history(session_id: str):
    """Get chat history for a session"""
    messages = await db.chat_messages.find(
        {"session_id": session_id},
        {"_id": 0, "role": 1, "content": 1, "created_at": 1}
    ).sort("created_at", 1).to_list(50)
    return messages

# ===================== INVOICE ROUTES =====================

@api_router.get("/invoice/{order_id}")
async def generate_invoice(order_id: str, request: Request, session_token: Optional[str] = Cookie(None)):
    """Generate PDF invoice for a completed order"""
    from fpdf import FPDF
    from fastapi.responses import StreamingResponse
    import io
    
    user = await require_auth(request, session_token)
    order = await db.orders.find_one(
        {"order_id": order_id, "user_id": user["user_id"], "status": "completed"},
        {"_id": 0}
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found or not completed")
    
    ebook = await db.ebooks.find_one({"ebook_id": order["ebook_id"]}, {"_id": 0})
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    # Header
    pdf.set_fill_color(10, 26, 15)
    pdf.rect(0, 0, 210, 40, 'F')
    pdf.set_text_color(80, 200, 120)
    pdf.set_font("Helvetica", "B", 24)
    pdf.set_xy(15, 10)
    pdf.cell(0, 10, "VigyaanKart", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(180, 180, 180)
    pdf.set_x(15)
    pdf.cell(0, 6, "The Science of Smart Earning", ln=True)
    
    # Invoice title
    pdf.set_y(50)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, "INVOICE", ln=True, align="C")
    pdf.ln(5)
    
    # Invoice details
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(100, 100, 100)
    inv_date = datetime.now(timezone.utc).strftime("%d %b %Y")
    pdf.cell(95, 7, f"Invoice No: INV-{order_id.upper()[-8:]}", ln=False)
    pdf.cell(95, 7, f"Date: {inv_date}", ln=True, align="R")
    pdf.ln(5)
    
    # Bill To
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 7, "Bill To:", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(0, 6, order.get("user_name", "Customer"), ln=True)
    pdf.cell(0, 6, order.get("user_email", ""), ln=True)
    pdf.ln(8)
    
    # Table header
    pdf.set_fill_color(240, 240, 240)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(90, 10, "Item", border=1, fill=True)
    pdf.cell(30, 10, "Qty", border=1, fill=True, align="C")
    pdf.cell(35, 10, "Price", border=1, fill=True, align="R")
    pdf.cell(35, 10, "Total", border=1, fill=True, align="R")
    pdf.ln()
    
    # Table row
    pdf.set_font("Helvetica", "", 10)
    title = ebook["title"] if ebook else order.get("ebook_title", "Ebook")
    pdf.cell(90, 10, title[:45], border=1)
    pdf.cell(30, 10, "1", border=1, align="C")
    pdf.cell(35, 10, f"Rs. {order['amount']:.2f}", border=1, align="R")
    pdf.cell(35, 10, f"Rs. {order['amount']:.2f}", border=1, align="R")
    pdf.ln(15)
    
    # Total
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(155, 10, "Total Amount:", align="R")
    pdf.cell(35, 10, f"Rs. {order['amount']:.2f}", align="R")
    pdf.ln(15)
    
    # Footer
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 6, "Thank you for your purchase!", ln=True, align="C")
    pdf.cell(0, 6, "VigyaanKart | support@vigyaankart.com | Mumbai, India", ln=True, align="C")
    
    pdf_bytes = pdf.output()
    buffer = io.BytesIO(pdf_bytes)
    buffer.seek(0)
    
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=invoice_{order_id}.pdf"}
    )

# ===================== UPSELL ROUTES =====================

@api_router.get("/upsell/{ebook_id}")
async def get_upsell_ebooks(ebook_id: str):
    """Get upsell recommendations after purchase"""
    ebook = await db.ebooks.find_one({"ebook_id": ebook_id}, {"_id": 0})
    if not ebook:
        return []
    related = await db.ebooks.find(
        {"category": ebook["category"], "ebook_id": {"$ne": ebook_id}, "is_active": True},
        {"_id": 0}
    ).to_list(2)
    if len(related) < 2:
        extra = await db.ebooks.find(
            {"ebook_id": {"$ne": ebook_id, "$nin": [r["ebook_id"] for r in related]}, "is_active": True},
            {"_id": 0}
        ).to_list(2 - len(related))
        related.extend(extra)
    return related

# ===================== EMAIL CAPTURE (EXIT INTENT) =====================

@api_router.post("/email-capture")
async def capture_email(request: Request):
    """Capture email from exit intent popup"""
    body = await request.json()
    email = body.get("email", "").strip()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    existing = await db.email_captures.find_one({"email": email})
    if not existing:
        await db.email_captures.insert_one({
            "email": email,
            "source": body.get("source", "exit_intent"),
            "created_at": datetime.now(timezone.utc).isoformat()
        })
    await send_mock_email(
        to_email=email,
        subject="Welcome to VigyaanKart! Here's Your Exclusive Offer",
        body=f"Hi there!\n\nThanks for subscribing to VigyaanKart. Use code WELCOME10 for 10% off your first ebook purchase.\n\nStart exploring: https://vigyaankart.com/ebooks\n\nTeam VigyaanKart"
    )
    return {"message": "Thank you! Check your email for an exclusive discount."}

# ===================== VIDEO TESTIMONIAL ROUTES =====================

@api_router.get("/video-testimonials")
async def get_video_testimonials():
    """Get published video testimonials"""
    testimonials = await db.video_testimonials.find(
        {"is_published": True}, {"_id": 0}
    ).sort("order", 1).to_list(20)
    return testimonials

@admin_router.get("/video-testimonials")
async def admin_get_video_testimonials(request: Request, session_token: Optional[str] = Cookie(None)):
    """Get all video testimonials for admin"""
    await require_admin(request, session_token)
    testimonials = await db.video_testimonials.find({}, {"_id": 0}).sort("order", 1).to_list(50)
    return testimonials

@admin_router.post("/video-testimonials")
async def admin_create_video_testimonial(request: Request, session_token: Optional[str] = Cookie(None)):
    """Create video testimonial"""
    await require_admin(request, session_token)
    body = await request.json()
    t = VideoTestimonial(**body)
    doc = t.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.video_testimonials.insert_one(doc)
    return {"testimonial_id": t.testimonial_id, "message": "Video testimonial created"}

@admin_router.put("/video-testimonials/{testimonial_id}")
async def admin_update_video_testimonial(testimonial_id: str, request: Request, session_token: Optional[str] = Cookie(None)):
    """Update video testimonial"""
    await require_admin(request, session_token)
    body = await request.json()
    body.pop("testimonial_id", None)
    body.pop("created_at", None)
    result = await db.video_testimonials.update_one({"testimonial_id": testimonial_id}, {"$set": body})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Testimonial not found")
    return {"message": "Video testimonial updated"}

@admin_router.delete("/video-testimonials/{testimonial_id}")
async def admin_delete_video_testimonial(testimonial_id: str, request: Request, session_token: Optional[str] = Cookie(None)):
    """Delete video testimonial"""
    await require_admin(request, session_token)
    result = await db.video_testimonials.delete_one({"testimonial_id": testimonial_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Testimonial not found")
    return {"message": "Video testimonial deleted"}

@admin_router.post("/upload/video")
async def admin_upload_video(request: Request, file: UploadFile = File(...), session_token: Optional[str] = Cookie(None)):
    """Upload a video file for testimonials"""
    await require_admin(request, session_token)
    allowed = ('.mp4', '.webm', '.mov')
    if not any(file.filename.lower().endswith(ext) for ext in allowed):
        raise HTTPException(status_code=400, detail="Only MP4, WebM, MOV videos are allowed")
    data = await file.read()
    if len(data) > 100 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 100MB)")
    ext = file.filename.split(".")[-1].lower()
    mime_map = {"mp4": "video/mp4", "webm": "video/webm", "mov": "video/quicktime"}
    path = f"{APP_NAME}/videos/{uuid.uuid4()}.{ext}"
    result = put_object(path, data, mime_map.get(ext, "video/mp4"))
    return {"path": result["path"], "filename": file.filename, "size": len(data)}

# ===================== REVIEW ROUTES =====================

@api_router.get("/reviews")
async def get_reviews():
    """Get published reviews for the landing page"""
    reviews = await db.reviews.find(
        {"is_published": True}, {"_id": 0}
    ).sort("order", 1).to_list(50)
    return reviews

@admin_router.get("/reviews")
async def admin_get_reviews(request: Request, session_token: Optional[str] = Cookie(None)):
    """Get all reviews for admin"""
    await require_admin(request, session_token)
    reviews = await db.reviews.find({}, {"_id": 0}).sort("order", 1).to_list(100)
    return reviews

@admin_router.post("/reviews")
async def admin_create_review(request: Request, session_token: Optional[str] = Cookie(None)):
    """Create a review"""
    await require_admin(request, session_token)
    body = await request.json()
    r = Review(**body)
    doc = r.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.reviews.insert_one(doc)
    return {"review_id": r.review_id, "message": "Review created"}

@admin_router.put("/reviews/{review_id}")
async def admin_update_review(review_id: str, request: Request, session_token: Optional[str] = Cookie(None)):
    """Update a review"""
    await require_admin(request, session_token)
    body = await request.json()
    body.pop("review_id", None)
    body.pop("created_at", None)
    result = await db.reviews.update_one({"review_id": review_id}, {"$set": body})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Review not found")
    return {"message": "Review updated"}

@admin_router.delete("/reviews/{review_id}")
async def admin_delete_review(review_id: str, request: Request, session_token: Optional[str] = Cookie(None)):
    """Delete a review"""
    await require_admin(request, session_token)
    result = await db.reviews.delete_one({"review_id": review_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Review not found")
    return {"message": "Review deleted"}

# ===================== SEED DATA =====================

@api_router.post("/seed-video-testimonials")
async def seed_video_testimonials():
    """Seed sample video testimonials"""
    existing = await db.video_testimonials.count_documents({})
    if existing > 0:
        return {"message": "Video testimonials already seeded"}
    samples = [
        {
            "name": "Rohit Sharma", "role": "Career Counsellor, Delhi",
            "thumbnail": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400",
            "embed_url": "https://www.youtube.com/embed/dQw4w9WgXcQ",
            "quote": "VigyaanKart's blueprint helped me start my own counselling business. Now earning ₹8L/month!",
            "rating": 5, "order": 1
        },
        {
            "name": "Priya Patel", "role": "AI Freelancer, Mumbai",
            "thumbnail": "https://images.unsplash.com/photo-1494790108755-2616b612b786?w=400",
            "embed_url": "https://www.youtube.com/embed/dQw4w9WgXcQ",
            "quote": "From zero to ₹5L/month using AI skills. The ebook was a game-changer for my freelancing career.",
            "rating": 5, "order": 2
        },
        {
            "name": "Amit Kumar", "role": "Import-Export Entrepreneur, Jaipur",
            "thumbnail": "https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=400",
            "embed_url": "https://www.youtube.com/embed/dQw4w9WgXcQ",
            "quote": "The import-export guide gave me step-by-step clarity. Closed my first international deal within 2 months!",
            "rating": 5, "order": 3
        }
    ]
    for s in samples:
        t = VideoTestimonial(**s)
        doc = t.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        await db.video_testimonials.insert_one(doc)
    return {"message": f"Seeded {len(samples)} video testimonials"}

@api_router.post("/seed-reviews")
async def seed_reviews():
    """Seed initial text reviews"""
    existing = await db.reviews.count_documents({})
    if existing > 0:
        return {"message": "Reviews already seeded"}
    samples = [
        {
            "name": "Rahul Sharma", "role": "Career Counselor",
            "image": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=100",
            "text": "The Career Counsellor Blueprint changed my life. I went from a 9-5 job to earning ₹8L/month within 6 months.",
            "rating": 5, "order": 1
        },
        {
            "name": "Priya Patel", "role": "Import-Export Business Owner",
            "image": "https://images.unsplash.com/photo-1494790108755-2616b612b47c?w=100",
            "text": "Started my import business with zero knowledge. Now doing ₹20L+ monthly revenue thanks to this guide.",
            "rating": 5, "order": 2
        },
        {
            "name": "Amit Kumar", "role": "Data Scientist",
            "image": "https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=100",
            "text": "The interview guide helped me crack interviews at top MNCs. Got a 3x salary hike!",
            "rating": 5, "order": 3
        }
    ]
    for s in samples:
        r = Review(**s)
        doc = r.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        await db.reviews.insert_one(doc)
    return {"message": f"Seeded {len(samples)} reviews"}

@api_router.post("/seed-ebooks")
async def seed_ebooks():
    """Seed initial ebooks data"""
    existing = await db.ebooks.count_documents({})
    if existing > 0:
        return {"message": "Ebooks already seeded"}
    
    ebooks_data = [
        {
            "title": "Career Counsellor Business Blueprint",
            "slug": "career-counsellor-business-blueprint",
            "description": "Complete guide to starting and scaling a profitable career counseling business in India. Learn how to help students make better career decisions while building a sustainable income stream.",
            "short_description": "Start your career counseling business and earn ₹5L-₹15L per month",
            "price": 1999,
            "original_price": 4999,
            "currency": "INR",
            "cover_image": "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=400",
            "category": "Business",
            "benefits": [
                "Step-by-step business setup guide",
                "Client acquisition strategies",
                "Pricing and packaging frameworks",
                "Marketing templates included",
                "Legal compliance checklist"
            ],
            "income_potential": "₹5 Lakh - ₹15 Lakh per month",
            "target_audience": "Educators, HR professionals, Psychology graduates, Aspiring entrepreneurs",
            "what_you_learn": [
                "Setting up your career counseling practice",
                "Getting certified and building credibility",
                "Finding and converting clients",
                "Conducting effective counseling sessions",
                "Scaling your business with team members"
            ],
            "countdown_hours": 24,
            "is_active": True
        },
        {
            "title": "Import Export Business Guide",
            "slug": "import-export-business-guide",
            "description": "Master the art of international trade with this comprehensive guide covering everything from product sourcing to customs clearance.",
            "short_description": "Learn to build a profitable import-export business from scratch",
            "price": 2499,
            "original_price": 5999,
            "currency": "INR",
            "cover_image": "https://images.unsplash.com/photo-1494412574643-ff11b0a5c1c3?w=400",
            "category": "Business",
            "benefits": [
                "Product sourcing strategies",
                "Legal documentation guide",
                "Customs and logistics explained",
                "Payment methods and LC",
                "Risk management techniques"
            ],
            "income_potential": "₹10 Lakh - ₹50 Lakh per month",
            "target_audience": "Aspiring traders, Business owners, Entrepreneurs",
            "what_you_learn": [
                "Finding profitable products to trade",
                "International supplier negotiations",
                "Export-Import documentation",
                "Shipping and logistics management",
                "Building long-term trade relationships"
            ],
            "countdown_hours": 24,
            "is_active": True
        },
        {
            "title": "Real Estate Income Blueprint",
            "slug": "real-estate-income-blueprint",
            "description": "Discover multiple income streams in real estate without investing crores. From brokerage to property management, learn it all.",
            "short_description": "Build passive income through real estate with minimal investment",
            "price": 1799,
            "original_price": 3999,
            "currency": "INR",
            "cover_image": "https://images.unsplash.com/photo-1560518883-ce09059eeffa?w=400",
            "category": "Real Estate",
            "benefits": [
                "Multiple income stream strategies",
                "Low investment entry points",
                "Property valuation techniques",
                "Negotiation scripts included",
                "Legal checklist for transactions"
            ],
            "income_potential": "₹3 Lakh - ₹20 Lakh per month",
            "target_audience": "Real estate enthusiasts, Investors, Side hustlers",
            "what_you_learn": [
                "Starting as a real estate consultant",
                "Property management services",
                "Real estate investment analysis",
                "Building a referral network",
                "Scaling with a team"
            ],
            "countdown_hours": 24,
            "is_active": True
        },
        {
            "title": "Top 10 AI Income Ideas",
            "slug": "top-10-ai-income-ideas",
            "description": "Leverage the AI revolution to create multiple income streams. From AI consulting to building AI-powered products, explore the opportunities.",
            "short_description": "Monetize AI skills and tools for consistent income",
            "price": 999,
            "original_price": 2499,
            "currency": "INR",
            "cover_image": "https://images.unsplash.com/photo-1677442136019-21780ecad995?w=400",
            "category": "Technology",
            "benefits": [
                "10 proven AI income models",
                "Tool recommendations",
                "Case studies included",
                "Step-by-step implementation",
                "Resource directory"
            ],
            "income_potential": "₹1 Lakh - ₹10 Lakh per month",
            "target_audience": "Tech enthusiasts, Freelancers, Digital marketers",
            "what_you_learn": [
                "AI content creation services",
                "AI automation consulting",
                "Building AI products",
                "AI training and workshops",
                "AI-powered marketing services"
            ],
            "countdown_hours": 24,
            "is_active": True
        },
        {
            "title": "Data Science Interview Guide",
            "slug": "data-science-interview-guide",
            "description": "Crack your data science, AI, ML, and cybersecurity interviews with this comprehensive preparation guide covering 500+ questions.",
            "short_description": "Land your dream job in AI/ML/Data Science with expert preparation",
            "price": 1499,
            "original_price": 3499,
            "currency": "INR",
            "cover_image": "https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=400",
            "category": "Career",
            "benefits": [
                "500+ interview questions",
                "Company-specific insights",
                "Coding problem solutions",
                "Behavioral question frameworks",
                "Salary negotiation tips"
            ],
            "income_potential": "₹15 LPA - ₹50 LPA packages",
            "target_audience": "Data science aspirants, Career changers, Fresh graduates",
            "what_you_learn": [
                "Core ML/AI concepts mastery",
                "Python and SQL proficiency",
                "Statistics and probability",
                "System design for ML",
                "Communication and presentation"
            ],
            "countdown_hours": 24,
            "is_active": True
        }
    ]
    
    for ebook_data in ebooks_data:
        ebook = Ebook(**ebook_data)
        doc = ebook.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        doc['updated_at'] = doc['updated_at'].isoformat()
        await db.ebooks.insert_one(doc)
    
    return {"message": f"Seeded {len(ebooks_data)} ebooks successfully"}

@api_router.post("/seed-admin")
async def seed_admin():
    """Create admin user (for testing)"""
    admin_email = "admin@vigyaankart.com"
    
    existing = await db.users.find_one({"email": admin_email})
    if existing:
        await db.users.update_one({"email": admin_email}, {"$set": {"role": "admin"}})
        return {"message": "Admin role updated"}
    
    admin = User(
        user_id=f"admin_{uuid.uuid4().hex[:12]}",
        email=admin_email,
        name="Admin User",
        role="admin"
    )
    
    doc = admin.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.users.insert_one(doc)
    
    return {"message": "Admin user created"}

@api_router.post("/seed-blog")
async def seed_blog():
    """Seed initial blog posts"""
    existing = await db.blog_posts.count_documents({})
    if existing > 0:
        return {"message": "Blog posts already seeded"}
    
    posts = [
        {
            "title": "How to Start a Career Counselling Business in India",
            "slug": "how-to-start-career-counselling-business",
            "excerpt": "India needs over 20 lakh career counselors. Learn how to tap into this massive opportunity and build a profitable counseling business from scratch.",
            "content": """## The Growing Demand for Career Counselors in India\n\nWith over 1.4 billion people and a rapidly evolving job market, India faces an acute shortage of qualified career counselors. The Supreme Court has directed schools to appoint career counselors, and CBSE has mandated expert career guidance in all schools.\n\n## Why Career Counselling is a Lucrative Business\n\n- **Growing demand**: 93% of Indian students are confused about career choices\n- **Low investment**: You can start with minimal infrastructure\n- **High returns**: Earn ₹5L–₹15L per month with the right approach\n- **Flexibility**: Work from home or set up a center\n\n## Steps to Get Started\n\n### 1. Get Certified\nObtain a recognized certification in career counselling. Several institutes offer online and offline programs.\n\n### 2. Choose Your Niche\nSpecialize in a particular area—school students, college admissions, working professionals, or international education.\n\n### 3. Build Your Online Presence\nCreate a professional website, list on Google My Business, and be active on LinkedIn and Instagram.\n\n### 4. Develop Your Service Packages\nOffer individual sessions, group workshops, school tie-ups, and online consultations.\n\n### 5. Scale with Technology\nUse assessment tools, CRM software, and video conferencing to serve more clients efficiently.\n\n## Income Potential\n\n| Service | Price Range | Monthly Potential |\n|---------|-------------|-------------------|\n| Individual Sessions | ₹1,500–₹5,000 | ₹1.5L–₹5L |\n| School Workshops | ₹15,000–₹50,000 | ₹3L–₹10L |\n| Online Courses | ₹2,000–₹10,000 | ₹2L–₹8L |\n\n## Conclusion\n\nThe career counselling industry in India is at an inflection point. With the right skills and business approach, you can build a highly rewarding career while making a real difference in people's lives.""",
            "cover_image": "https://images.unsplash.com/photo-1522202176988-66273c2fd55f?w=800",
            "author": "VigyaanKart Team",
            "category": "Career",
            "tags": ["career counselling", "business", "startup", "education"],
            "read_time": 8,
            "is_published": True
        },
        {
            "title": "Top 10 Ways to Make Money with AI in 2026",
            "slug": "top-10-ways-make-money-with-ai-2026",
            "excerpt": "AI is transforming every industry. Discover the top 10 proven ways to leverage AI tools and skills to build sustainable income streams.",
            "content": """## AI is the Biggest Opportunity of Our Lifetime\n\nArtificial Intelligence is not just a technology trend—it is a fundamental shift in how businesses operate and how value is created. Here are the top 10 ways you can leverage AI to earn money in 2026.\n\n## 1. AI Content Creation Agency\nOffer content writing, social media management, and copywriting services using AI tools. Charge ₹50,000–₹2L per month per client.\n\n## 2. AI Automation Consulting\nHelp businesses automate repetitive tasks using AI. From customer service bots to data processing—there is huge demand for automation experts.\n\n## 3. AI-Powered Marketing Services\nUse AI for ad optimization, email marketing, and SEO. Businesses are willing to pay premium rates for data-driven marketing.\n\n## 4. Build and Sell AI Products\nCreate AI-powered tools, Chrome extensions, or SaaS products. Even simple tools can generate significant recurring revenue.\n\n## 5. AI Training and Workshops\nConduct corporate training sessions on AI tools and productivity. Companies are spending lakhs on upskilling their workforce.\n\n## 6. AI Video Production\nUse AI for video editing, voice-over, and content creation. YouTube channels and businesses need constant video content.\n\n## 7. AI-Powered E-commerce\nLeverage AI for product research, listing optimization, and customer service in e-commerce businesses.\n\n## 8. AI Data Analysis Services\nOffer data analysis and visualization services to SMBs that cannot afford full-time analysts.\n\n## 9. AI Tutoring Platform\nBuild an AI-enhanced tutoring service combining AI tools with human expertise for personalized education.\n\n## 10. AI Freelancing on Global Platforms\nOffer AI-related services on Upwork, Fiverr, and Toptal. The global demand for AI skills far exceeds supply.\n\n## Getting Started\n\nThe key is to pick one area, build expertise, and start small. Most of these can be started with minimal investment—your main capital is knowledge and effort.\n\nOur **Top 10 AI Income Ideas** ebook provides detailed roadmaps for each of these opportunities.""",
            "cover_image": "https://images.unsplash.com/photo-1677442136019-21780ecad995?w=800",
            "author": "VigyaanKart Team",
            "category": "Technology",
            "tags": ["AI", "income", "technology", "freelancing"],
            "read_time": 6,
            "is_published": True
        },
        {
            "title": "Import Export Business: A Complete Beginner's Guide",
            "slug": "import-export-business-beginners-guide",
            "excerpt": "Learn the fundamentals of starting an import-export business in India. From documentation to finding international buyers—everything you need to know.",
            "content": """## Why Import-Export is a Great Business Opportunity\n\nIndia's foreign trade crossed $1 trillion in recent years, and the government is actively promoting exports through various schemes. This creates an enormous opportunity for new entrepreneurs.\n\n## Understanding the Basics\n\n### What is Import-Export Business?\nIt involves buying goods from one country and selling them in another. You act as a bridge between manufacturers and markets across borders.\n\n### Key Requirements\n- **IEC (Import Export Code)**: The basic license needed, obtainable online from DGFT\n- **GST Registration**: Mandatory for international trade\n- **Bank Account**: Current account with a bank that handles forex\n- **RCMC**: Registration-cum-Membership Certificate from relevant export council\n\n## Steps to Start\n\n### Step 1: Choose Your Products\nResearch products with high demand in international markets. Look for products where India has a competitive advantage.\n\n### Step 2: Get Your Documentation Right\nObtain IEC, register with the relevant export promotion council, and set up a GST-compliant invoicing system.\n\n### Step 3: Find Buyers/Suppliers\nUse platforms like Alibaba, IndiaMART, trade fairs, and embassy commercial sections to find partners.\n\n### Step 4: Understand Shipping and Logistics\nLearn about Incoterms, shipping methods (FCL, LCL), insurance, and customs clearance procedures.\n\n### Step 5: Handle Payments Securely\nUse Letters of Credit (LC), advance payments, or escrow services to minimize payment risks.\n\n## Common Mistakes to Avoid\n\n1. Not researching the market thoroughly\n2. Ignoring quality control\n3. Underestimating shipping costs\n4. Not getting proper insurance\n5. Choosing unreliable logistics partners\n\n## Revenue Potential\n\nStarting with modest trades, you can scale to ₹10L–₹50L monthly revenue within 1-2 years with consistent effort and smart decisions.\n\nFor a detailed step-by-step roadmap, check out our **Import Export Business Guide** ebook.""",
            "cover_image": "https://images.unsplash.com/photo-1494412574643-ff11b0a5c1c3?w=800",
            "author": "VigyaanKart Team",
            "category": "Business",
            "tags": ["import export", "business", "international trade", "startup"],
            "read_time": 10,
            "is_published": True
        },
        {
            "title": "5 Real Estate Investment Strategies for Beginners",
            "slug": "real-estate-investment-strategies-beginners",
            "excerpt": "You don't need crores to invest in real estate. Discover 5 proven strategies to start earning from real estate with minimal investment.",
            "content": """## Real Estate: The Wealth-Building Asset Class\n\nReal estate has created more millionaires than any other asset class. But you don't need huge capital to get started.\n\n## Strategy 1: Real Estate Consulting\nBecome a property consultant or broker. Help buyers find properties and earn 1-2% commission on each deal.\n\n**Investment needed**: Minimal (₹50,000 for setup)\n**Income potential**: ₹3L–₹15L per month\n\n## Strategy 2: Rental Arbitrage\nRent properties on long-term leases and sub-let them as furnished rentals or serviced apartments at higher rates.\n\n**Investment needed**: ₹2–5L (furnishing + deposits)\n**Income potential**: ₹50,000–₹3L per month per property\n\n## Strategy 3: Real Estate Digital Marketing\nHelp builders and developers sell properties through digital marketing. This is a high-margin service business.\n\n**Investment needed**: ₹1L (tools + ads)\n**Income potential**: ₹2L–₹10L per month\n\n## Strategy 4: REITs (Real Estate Investment Trusts)\nInvest in listed REITs on stock exchanges. Get exposure to commercial real estate with as little as ₹500.\n\n**Investment needed**: Any amount\n**Income potential**: 6-8% annual returns + capital appreciation\n\n## Strategy 5: Property Management Services\nManage rental properties for NRI owners or busy landlords. Charge monthly management fees.\n\n**Investment needed**: Minimal\n**Income potential**: ₹1L–₹5L per month\n\n## Getting Started\n\nThe key is to start with low-risk strategies and gradually move to higher-investment opportunities as you build expertise and capital.\n\nOur **Real Estate Income Blueprint** provides detailed playbooks for each of these strategies.""",
            "cover_image": "https://images.unsplash.com/photo-1560518883-ce09059eeffa?w=800",
            "author": "VigyaanKart Team",
            "category": "Real Estate",
            "tags": ["real estate", "investment", "passive income", "property"],
            "read_time": 7,
            "is_published": True
        },
        {
            "title": "How to Crack Data Science Interviews in 2026",
            "slug": "crack-data-science-interviews-2026",
            "excerpt": "A comprehensive guide to preparing for data science, ML, and AI interviews at top companies. Tips, strategies, and common mistakes to avoid.",
            "content": """## The Data Science Job Market in 2026\n\nData science continues to be one of the highest-paying and most in-demand career paths globally. With AI adoption accelerating, companies are aggressively hiring data talent.\n\n## Interview Preparation Roadmap\n\n### Phase 1: Strengthen Fundamentals (2-4 weeks)\n- **Statistics & Probability**: Distributions, hypothesis testing, Bayesian inference\n- **Linear Algebra**: Vectors, matrices, eigenvalues\n- **Calculus**: Derivatives, gradients, optimization\n\n### Phase 2: Technical Skills (4-6 weeks)\n- **Python/R**: Pandas, NumPy, Scikit-learn mastery\n- **SQL**: Complex queries, window functions, optimization\n- **ML Algorithms**: Regression, classification, clustering, deep learning\n\n### Phase 3: System Design (2-3 weeks)\n- ML system architecture\n- Data pipeline design\n- Scalability and monitoring\n\n### Phase 4: Mock Interviews (2 weeks)\n- Practice with peers or platforms\n- Behavioral question preparation\n- Case study practice\n\n## Common Interview Questions\n\n1. Explain the bias-variance tradeoff\n2. How would you handle imbalanced datasets?\n3. Describe a time you used data to influence a business decision\n4. Design a recommendation system for an e-commerce platform\n5. Walk me through your approach to a classification problem\n\n## Salary Expectations\n\n| Experience | Expected Package |\n|-----------|------------------|\n| 0-2 years | ₹8–15 LPA |\n| 2-5 years | ₹15–35 LPA |\n| 5+ years | ₹35–70 LPA |\n\n## Pro Tips\n\n- Focus on understanding concepts, not memorizing answers\n- Work on real projects and be ready to discuss them in depth\n- Practice explaining complex topics simply\n- Stay updated with latest papers and industry trends\n\nFor 500+ curated interview questions with detailed solutions, get our **Data Science Interview Guide** ebook.""",
            "cover_image": "https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=800",
            "author": "VigyaanKart Team",
            "category": "Career",
            "tags": ["data science", "interview", "career", "AI", "ML"],
            "read_time": 9,
            "is_published": True
        }
    ]
    
    for post_data in posts:
        post = BlogPost(**post_data)
        doc = post.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        doc['updated_at'] = doc['updated_at'].isoformat()
        await db.blog_posts.insert_one(doc)
    
    return {"message": f"Seeded {len(posts)} blog posts successfully"}

@api_router.get("/")
async def root():
    return {"message": "VigyaanKart API v1.0", "status": "healthy"}

# Include all routers
api_router.include_router(auth_router)
api_router.include_router(ebook_router)
api_router.include_router(order_router)
api_router.include_router(payment_router)
api_router.include_router(admin_router)
api_router.include_router(user_router)
api_router.include_router(coupon_router)
api_router.include_router(blog_router)
api_router.include_router(contact_router)
api_router.include_router(affiliate_router)
api_router.include_router(chat_router)

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()

@app.on_event("startup")
async def startup_init():
    try:
        init_storage()
        logger.info("Object storage initialized")
    except Exception as e:
        logger.warning(f"Storage init deferred: {e}")
    # Seed reviews if none exist
    try:
        review_count = await db.reviews.count_documents({})
        if review_count == 0:
            await seed_reviews()
            logger.info("Seeded initial reviews")
    except Exception as e:
        logger.warning(f"Review seeding deferred: {e}")
