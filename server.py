from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, validator
from typing import List, Optional
import uuid
from datetime import datetime, timedelta
import json
import googlemaps
import re
from enum import Enum

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ.get('DB_NAME', 'dealdish_prod')]

# Google Maps client
gmaps = googlemaps.Client(key=os.environ.get('GOOGLE_MAPS_API_KEY'))

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Enums
class UserType(str, Enum):
    customer = "customer"
    restaurant = "restaurant"

class SubscriptionStatus(str, Enum):
    trial = "trial"
    active = "active"
    expired = "expired"
    cancelled = "cancelled"

class CommissionTier(str, Enum):
    trial = "trial"  # 10% for first month
    standard = "standard"  # 15% after first month
# Models
class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    name: str
    mobile_number: str
    user_type: UserType
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Subscription fields
    subscription_status: SubscriptionStatus = SubscriptionStatus.trial
    trial_end_date: Optional[datetime] = None  # Only for customers
    subscription_end_date: Optional[datetime] = None
    commission_tier: CommissionTier = CommissionTier.trial
    
    @validator('mobile_number')
    def validate_mobile_number(cls, v):
        # Australian mobile number validation
        pattern = r'^(\+61|0)[4-5]\d{8}$'
        if not re.match(pattern, v):
            raise ValueError('Invalid Australian mobile number format')
        return v
    
    @validator('email')
    def validate_email(cls, v):
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, v):
            raise ValueError('Invalid email format')
        return v

class UserCreate(BaseModel):
    email: str
    name: str
    mobile_number: str
    user_type: UserType

class Subscription(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    plan_name: str = "DealDish Pro"
    price_aud: float = 7.0
    currency: str = "AUD"
    billing_cycle: str = "monthly"
    status: SubscriptionStatus
    trial_end_date: Optional[datetime] = None
    next_billing_date: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    cancelled_at: Optional[datetime] = None

class Restaurant(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    name: str
    address: str
    cuisine_type: str
    description: str
    image_url: str
    rating: float = 4.5
    is_active: bool = True
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    
    # Commission fields
    commission_rate: float = 0.10  # 10% for trial, 15% for standard
    total_commission_paid: float = 0.0
    orders_count: int = 0
    
    created_at: datetime = Field(default_factory=datetime.utcnow)

class RestaurantCreate(BaseModel):
    name: str
    address: str
    cuisine_type: str
    description: str
    image_url: str
  class FoodItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    restaurant_id: str
    name: str
    description: str
    original_price: float
    discounted_price: float
    discount_percentage: int
    image_url: str
    cuisine_type: str
    dietary_restrictions: List[str] = []
    quantity_available: int
    expires_at: datetime
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_available: bool = True

class FoodItemCreate(BaseModel):
    restaurant_id: str
    name: str
    description: str
    original_price: float
    discounted_price: float
    image_url: str
    cuisine_type: str
    dietary_restrictions: List[str] = []
    quantity_available: int
    expires_at: datetime

class Order(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    customer_id: str
    restaurant_id: str
    food_items: List[dict]
    total_amount: float
    commission_amount: float
    commission_rate: float
    status: str = "pending"  # pending, confirmed, ready, completed, cancelled
    pickup_time: datetime
    qr_code: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

class OrderCreate(BaseModel):
    customer_id: str
    restaurant_id: str
    food_items: List[dict]
    total_amount: float
    pickup_time: datetime

class LocationSearch(BaseModel):
    latitude: float
    longitude: float
    radius: int = 5000  # meters

# Helper functions
def get_commission_rate(user_id: str) -> float:
    """Get current commission rate for a restaurant based on their subscription tier"""
    return 0.10  # 10% for trial month

def calculate_commission(total_amount: float, commission_rate: float) -> float:
    """Calculate commission amount"""
    return total_amount * commission_rate

def is_trial_period_active(user: User) -> bool:
    """Check if user's trial period is still active"""
    if user.trial_end_date:
        return datetime.utcnow() < user.trial_end_date
    return False

def geocode_address(address: str):
    try:
        geocode_result = gmaps.geocode(address)
        if geocode_result:
            location = geocode_result[0]['geometry']['location']
            return location['lat'], location['lng']
    except Exception as e:
        print(f"Geocoding error: {e}")
    return None, None
  # Auth routes
@api_router.post("/auth/register", response_model=User)
async def register_user(user: UserCreate):
    # Check if user already exists by email
    existing_user = await db.users.find_one({"email": user.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="User with this email already exists")
    
    # Check if mobile number already exists
    existing_mobile = await db.users.find_one({"mobile_number": user.mobile_number})
    if existing_mobile:
        raise HTTPException(status_code=400, detail="User with this mobile number already exists")
    
    # Create user with correct subscription model
    user_obj = User(**user.dict())
    
    # Set subscription details based on user type
    if user.user_type == UserType.customer:
        # Customers get 1 month free trial
        user_obj.subscription_status = SubscriptionStatus.trial
        user_obj.trial_end_date = datetime.utcnow() + timedelta(days=30)
        user_obj.commission_tier = CommissionTier.trial
    else:
        # Restaurants get free signup (no subscription)
        user_obj.subscription_status = SubscriptionStatus.active
        user_obj.commission_tier = CommissionTier.trial
    
    await db.users.insert_one(user_obj.dict())
    
    # Create subscription record for customers only
    if user.user_type == UserType.customer:
        subscription = Subscription(
            user_id=user_obj.id,
            status=SubscriptionStatus.trial,
            trial_end_date=user_obj.trial_end_date
        )
        await db.subscriptions.insert_one(subscription.dict())
    
    return user_obj

@api_router.post("/auth/login")
async def login_user(email: str, password: str = "demo"):
    user = await db.users.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    user_obj = User(**user)
    
    # Check if trial period has expired for customer users
    if user_obj.user_type == UserType.customer and user_obj.trial_end_date:
        if not is_trial_period_active(user_obj):
            if user_obj.subscription_status == SubscriptionStatus.trial:
                # Update to expired status
                await db.users.update_one(
                    {"id": user_obj.id},
                    {"$set": {"subscription_status": SubscriptionStatus.expired}}
                )
                user_obj.subscription_status = SubscriptionStatus.expired
    
    return {"user": user_obj, "token": "demo-token"}

# Restaurant routes
@api_router.get("/restaurants")
async def get_restaurants():
    restaurants = await db.restaurants.find({"is_active": True}).to_list(100)
    return restaurants

@api_router.post("/restaurants")
async def create_restaurant(restaurant: RestaurantCreate, user_id: str = "demo-user"):
    lat, lng = geocode_address(restaurant.address)
    
    restaurant_obj = Restaurant(
        **restaurant.dict(), 
        user_id=user_id,
        latitude=lat,
        longitude=lng,
        commission_rate=0.10
    )
    await db.restaurants.insert_one(restaurant_obj.dict())
    return restaurant_obj
  # Food item routes
@api_router.get("/food-items")
async def get_food_items(cuisine_type: Optional[str] = None, dietary_restrictions: Optional[str] = None):
    query = {"is_available": True, "expires_at": {"$gte": datetime.utcnow()}}
    
    if cuisine_type:
        query["cuisine_type"] = cuisine_type
    
    if dietary_restrictions:
        query["dietary_restrictions"] = {"$in": dietary_restrictions.split(",")}
    
    food_items = await db.food_items.find(query).to_list(100)
    return food_items

@api_router.post("/food-items")
async def create_food_item(food_item: FoodItemCreate):
    discount_percentage = int(((food_item.original_price - food_item.discounted_price) / food_item.original_price) * 100)
    
    food_item_obj = FoodItem(**food_item.dict(), discount_percentage=discount_percentage)
    await db.food_items.insert_one(food_item_obj.dict())
    return food_item_obj

# Order routes
@api_router.post("/orders")
async def create_order(order: OrderCreate):
    restaurant = await db.restaurants.find_one({"id": order.restaurant_id})
    if not restaurant:
        raise HTTPException(status_code=404, detail="Restaurant not found")
    
    commission_rate = restaurant.get("commission_rate", 0.10)
    commission_amount = calculate_commission(order.total_amount, commission_rate)
    
    qr_code = str(uuid.uuid4())
    order_obj = Order(
        **order.dict(), 
        qr_code=qr_code,
        commission_amount=commission_amount,
        commission_rate=commission_rate
    )
    await db.orders.insert_one(order_obj.dict())
    return order_obj

# Analytics routes
@api_router.get("/analytics/food-waste-saved")
async def get_food_waste_saved():
    total_orders = await db.orders.count_documents({"status": "completed"})
    estimated_waste_saved = total_orders * 0.5  # Assume 0.5kg per order
    return {"total_waste_saved_kg": estimated_waste_saved, "total_orders": total_orders}

# Demo data population
@api_router.post("/demo/populate")
async def populate_demo_data():
    # Clear existing data
    await db.restaurants.delete_many({})
    await db.food_items.delete_many({})
    
    # Create demo restaurants
    demo_restaurants = [
        {
            "id": str(uuid.uuid4()),
            "user_id": "demo-user",
            "name": "Luigi's Italian Kitchen",
            "address": "123 Collins Street, Melbourne VIC 3000",
            "cuisine_type": "Italian",
            "description": "Authentic Italian cuisine in the heart of Melbourne",
            "image_url": "https://images.unsplash.com/photo-1600891964599-f61ba0e24092?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NDk1NzZ8MHwxfHNlYXJjaHwxfHxyZXN0YXVyYW50JTIwZm9vZHxlbnwwfHx8fDE3NTI2NTUxMTB8MA&ixlib=rb-4.1.0&q=85",
            "rating": 4.5,
            "is_active": True,
            "commission_rate": 0.10,
            "total_commission_paid": 0.0,
            "orders_count": 0,
            "created_at": datetime.utcnow()
        }
    ]
    
    await db.restaurants.insert_many(demo_restaurants)
    
    # Create demo food items
    demo_food_items = []
    for restaurant in demo_restaurants:
        for i in range(3):
            expires_at = datetime.utcnow() + timedelta(hours=2 + i)
            demo_food_items.append({
                "id": str(uuid.uuid4()),
                "restaurant_id": restaurant["id"],
                "name": f"Chef's Special {i+1}",
                "description": f"Delicious {restaurant['cuisine_type']} dish prepared fresh today",
                "original_price": 25.0 + (i * 5),
                "discounted_price": 15.0 + (i * 3),
                "discount_percentage": 40,
                "image_url": restaurant["image_url"],
                "cuisine_type": restaurant["cuisine_type"],
                "dietary_restrictions": ["vegetarian"] if i == 0 else [],
                "quantity_available": 5 - i,
                "expires_at": expires_at,
                "created_at": datetime.utcnow(),
                "is_available": True
            })
    
    await db.food_items.insert_many(demo_food_items)
    return {"message": "Demo data populated successfully"}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
