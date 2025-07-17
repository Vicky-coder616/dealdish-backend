from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from motor.motor_asyncio import AsyncIOMotorClient
from typing import List, Optional
import os
import uvicorn
import uuid
from datetime import datetime, timedelta

app = FastAPI(title="DealDish API", description="Food waste reduction platform")

# MongoDB connection
mongo_url = os.environ.get('MONGO_URL')
if mongo_url:
    client = AsyncIOMotorClient(mongo_url)
    db = client[os.environ.get('DB_NAME', 'dealdish_prod')]
else:
    client = None
    db = None

# Models
class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    name: str
    mobile_number: str
    user_type: str  # 'customer' or 'restaurant'
    created_at: datetime = Field(default_factory=datetime.utcnow)

class UserCreate(BaseModel):
    email: str
    name: str
    mobile_number: str
    user_type: str

class Restaurant(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    address: str
    cuisine_type: str
    description: str
    rating: float = 4.5
    commission_rate: float = 0.10
    created_at: datetime = Field(default_factory=datetime.utcnow)

class FoodItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    restaurant_id: str
    name: str
    description: str
    original_price: float
    discounted_price: float
    discount_percentage: int
    quantity_available: int
    expires_at: datetime
    created_at: datetime = Field(default_factory=datetime.utcnow)

# Basic endpoints
@app.get("/")
async def root():
    return {"message": "DealDish API is running!", "status": "success"}

@app.get("/api/health")
async def health():
    return {"status": "healthy", "app": "dealdish-backend", "database": "connected" if db else "not configured"}

# Analytics
@app.get("/api/analytics/food-waste-saved")
async def get_food_waste_saved():
    if db:
        # Real data from database
        orders_count = await db.orders.count_documents({}) if await db.orders.count_documents({}) else 0
        waste_saved = orders_count * 0.5
    else:
        # Demo data
        waste_saved = 150.5
        orders_count = 42
    return {"total_waste_saved_kg": waste_saved, "total_orders": orders_count}

# User registration
@app.post("/api/auth/register")
async def register_user(user: UserCreate):
    if not db:
        return {"message": "Database not configured", "user": user.dict()}
    
    # Check if user exists
    existing_user = await db.users.find_one({"email": user.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")
    
    user_obj = User(**user.dict())
    await db.users.insert_one(user_obj.dict())
    return {"message": "User registered successfully", "user": user_obj}

# Get restaurants
@app.get("/api/restaurants")
async def get_restaurants():
    if not db:
        # Demo data
        return [
            {
                "id": "demo-1",
                "name": "Luigi's Italian Kitchen",
                "address": "123 Collins Street, Melbourne",
                "cuisine_type": "Italian",
                "description": "Authentic Italian cuisine",
                "rating": 4.5
            }
        ]
    
    restaurants = await db.restaurants.find({}).to_list(100)
    return restaurants

# Demo data population
@app.post("/api/demo/populate")
async def populate_demo_data():
    if not db:
        return {"message": "Database not configured - using demo data"}
    
    # Clear existing data
    await db.restaurants.delete_many({})
    await db.food_items.delete_many({})
    
    # Create demo restaurant
    demo_restaurant = {
        "id": str(uuid.uuid4()),
        "name": "Luigi's Italian Kitchen",
        "address": "123 Collins Street, Melbourne VIC 3000",
        "cuisine_type": "Italian", 
        "description": "Authentic Italian cuisine in the heart of Melbourne",
        "rating": 4.5,
        "commission_rate": 0.10,
        "created_at": datetime.utcnow()
    }
    
    await db.restaurants.insert_one(demo_restaurant)
    
    # Create demo food items
    for i in range(3):
        expires_at = datetime.utcnow() + timedelta(hours=2 + i)
        food_item = {
            "id": str(uuid.uuid4()),
            "restaurant_id": demo_restaurant["id"],
            "name": f"Chef's Special {i+1}",
            "description": f"Delicious Italian dish prepared fresh today",
            "original_price": 25.0 + (i * 5),
            "discounted_price": 15.0 + (i * 3),
            "discount_percentage": 40,
            "quantity_available": 5 - i,
            "expires_at": expires_at,
            "created_at": datetime.utcnow()
        }
        await db.food_items.insert_one(food_item)
    
    return {"message": "Demo data populated successfully"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
