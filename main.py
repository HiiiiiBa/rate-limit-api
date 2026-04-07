from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from rate_limiter import rate_limiter

app = FastAPI()

@app.middleware("http")
async def limit_middleware(request: Request, call_next):
    try:
        rate_limiter(request)
        response = await call_next(request)
        return response
    except HTTPException as e:
        return JSONResponse(
            status_code=e.status_code,
            content={"detail": e.detail}
        )

@app.get("/")
def home():
    return {"message": "API fonctionne"}

@app.get("/users")
def users():
    return {"users": ["Ahmed", "Sara", "Ali"]}

@app.get("/products")
def products():
    return {"products": ["Laptop", "Phone", "Tablet"]}