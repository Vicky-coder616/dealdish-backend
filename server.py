from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional
import os
import uvicorn
import uuid
from datetime import datetime, timedelta

app = FastAPI(title="DealDish API", description="Food waste reduction platform")

# In-memory storage (temporary)
users_db = []
restaurants_db = []
food_items_db = []
orders_db = []

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
    return {"message": "DealDish API is running!", "status": "success", "version": "2.0"}

@app.get("/api/health")
async def health():
    return {
        "status": "healthy", 
        "app": "dealdish-backend", 
        "database": "in-memory",
        "restaurants_count": len(restaurants_db),
        "food_items_count": len(food_items_db)
    }

# Analytics
@app.get("/api/analytics/food-waste-saved")
async def get_food_waste_saved():
    orders_count = len(orders_db)
    waste_saved = orders_count * 0.5
    return {"total_waste_saved_kg": waste_saved, "total_orders": orders_count}

# User registration
@app.post("/api/auth/register")
async def register_user(user: UserCreate):
    # Check if user exists
    existing_user = next((u for u in users_db if u["email"] == user.email), None)
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")
    
    user_obj = User(**user.dict())
    users_db.append(user_obj.dict())
    return {"message": "User registered successfully", "user": user_obj}

# Get restaurants
@app.get("/api/restaurants")
async def get_restaurants():
    return restaurants_db

# Get food items
@app.get("/api/food-items")
async def get_food_items():
    # Filter out expired items
    current_time = datetime.utcnow()
    active_items = [item for item in food_items_db if datetime.fromisoformat(item["expires_at"].replace("Z", "+00:00")) > current_time]
    return active_items

# Demo data population
@app.post("/api/demo/populate")
async def populate_demo_data():
    global restaurants_db, food_items_db
    
    # Clear existing data
    restaurants_db.clear()
    food_items_db.clear()
    
    # Create demo restaurants
    demo_restaurants = [
        {
            "id": str(uuid.uuid4()),
            "name": "Luigi's Italian Kitchen",
            "address": "123 Collins Street, Melbourne VIC 3000",
            "cuisine_type": "Italian", 
            "description": "Authentic Italian cuisine in the heart of Melbourne",
            "rating": 4.5,
            "commission_rate": 0.10,
            "created_at": datetime.utcnow().isoformat()
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Green Garden Bistro",
            "address": "456 Flinders Lane, Melbourne VIC 3000",
            "cuisine_type": "Healthy", 
            "description": "Fresh, sustainable dining with locally sourced ingredients",
            "rating": 4.7,
            "commission_rate": 0.10,
            "created_at": datetime.utcnow().isoformat()
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Spice Route",
            "address": "789 Chapel Street, South Yarra VIC 3141",
            "cuisine_type": "Indian", 
            "description": "Traditional Indian flavors with modern presentation",
            "rating": 4.3,
            "commission_rate": 0.10,
            "created_at": datetime.utcnow().isoformat()
        }
    ]
    
    restaurants_db.extend(demo_restaurants)
    
    # Create demo food items for each restaurant
    for restaurant in demo_restaurants:
        for i in range(3):
            expires_at = datetime.utcnow() + timedelta(hours=2 + i)
            food_item = {
                "id": str(uuid.uuid4()),
                "restaurant_id": restaurant["id"],
                "name": f"Chef's Special {i+1}",
                "description": f"Delicious {restaurant['cuisine_type']} dish prepared fresh today",
                "original_price": 25.0 + (i * 5),
                "discounted_price": 15.0 + (i * 3),
                "discount_percentage": 40,
                "quantity_available": 5 - i,
                "expires_at": expires_at.isoformat(),
                "created_at": datetime.utcnow().isoformat()
            }
            food_items_db.append(food_item)
    
    return {
        "message": "Demo data populated successfully",
        "restaurants_created": len(demo_restaurants),
        "food_items_created": len(demo_restaurants) * 3
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
