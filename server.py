from fastapi import FastAPI
import os
import uvicorn

app = FastAPI(title="DealDish API")

@app.get("/")
async def root():
    return {"message": "DealDish API is running!", "status": "success"}

@app.get("/api/health")
async def health():
    return {"status": "healthy", "app": "dealdish-backend"}

@app.get("/api/analytics/food-waste-saved")
async def get_food_waste_saved():
    return {"total_waste_saved_kg": 150.5, "total_orders": 42}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
