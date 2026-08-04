from fastapi import FastAPI

app = FastAPI(title="İK Asistanı API")


@app.get("/")
def read_root():
    return {"status": "ok", "message": "İK Asistanı API çalışıyor"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}
