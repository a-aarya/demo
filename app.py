from fastapi import FastAPI
from pydantic import BaseModel
from search import search_products  

app = FastAPI()

class QueryRequest(BaseModel):
    query: str

@app.get("/")
def root():
    return {"status": "API running"}

@app.post("/search")
def search(request: QueryRequest):
    return search_products(request.query)
