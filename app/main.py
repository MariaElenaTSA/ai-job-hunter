from fastapi import FastAPI

app = FastAPI(
    title="AI Job Hunter",
    version="0.1.0"
)

@app.get("/")
def home():
    return {"message": "AI Job Hunter API is running!"}

@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "AI Job Hunter",
        "version": "0.1.0"
    }

@app.get("/jobs")
def get_jobs():
    return [
        {
            "company": "Stripe",
            "title": "Solutions Engineer",
            "location": "Remote",
            "score": 98
        },
        {
            "company": "Brex",
            "title": "Product Operations",
            "location": "Remote",
            "score": 96
        }
    ]