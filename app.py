import sqlite3
import json
import os
from fastapi import FastAPI, HTTPException, Depends, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer
from datetime import datetime, time
import uvicorn
from pydantic import BaseModel
import hashlib

app = FastAPI()

# Mount static files directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)  # Create static directory if it doesn't exist
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Global start time (00:00 hours)
GLOBAL_START_TIME = datetime.combine(datetime.today(), time(0, 0))

# OAuth2 scheme for token (simplified)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# Database file path
DB_PATH = os.path.join(BASE_DIR, "database.db")

# Initialize database
def init_db():
    # Ensure the database directory exists
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create users table with password
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            sequence TEXT NOT NULL,
            password TEXT NOT NULL
        )
    """)
    
    # Create videos table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS videos (
            user_id TEXT,
            video_name TEXT,
            duration INTEGER,
            PRIMARY KEY (user_id, video_name),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)
    
    # Insert sample data only if it doesn't already exist
    cursor.execute("SELECT COUNT(*) FROM users WHERE user_id = 'user1'")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO users (user_id, sequence, password) VALUES (?, ?, ?)",
                       ("user1", '["video1", "video2", "video3"]', hashlib.sha256("password1".encode()).hexdigest()))
        cursor.executemany("INSERT INTO videos (user_id, video_name, duration) VALUES (?, ?, ?)",
                          [("user1", "video1", 45), ("user1", "video2", 50), ("user1", "video3", 55)])
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE user_id = 'user2'")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO users (user_id, sequence, password) VALUES (?, ?, ?)",
                       ("user2", '["video1", "video2", "video3"]', hashlib.sha256("password2".encode()).hexdigest()))
        cursor.executemany("INSERT INTO videos (user_id, video_name, duration) VALUES (?, ?, ?)",
                          [("user2", "video1", 45), ("user2", "video2", 50), ("user2", "video3", 55)])
    
    conn.commit()
    conn.close()

# User model for login
class UserLogin(BaseModel):
    username: str
    password: str

def get_user_sequence(user_id: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT sequence FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    if not result:
        raise HTTPException(status_code=404, detail="User not found")
    return json.loads(result[0])

def get_video_duration(user_id: str, video_name: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT duration FROM videos WHERE user_id = ? AND video_name = ?",
                   (user_id, video_name))
    result = cursor.fetchone()
    conn.close()
    if not result:
        raise HTTPException(status_code=404, detail="Video not found")
    return result[0]

def verify_user(username: str, password: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM users WHERE user_id = ?", (username,))
    result = cursor.fetchone()
    conn.close()
    if not result or result[0] != hashlib.sha256(password.encode()).hexdigest():
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return username

@app.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    user_id = verify_user(username, password)
    return {"access_token": user_id, "token_type": "bearer"}

@app.get("/stream/{user_id}")
async def stream(user_id: str, token: str = Depends(oauth2_scheme)):
    if token != user_id:  # Simplified token check
        raise HTTPException(status_code=401, detail="Invalid token")
    
    sequence = get_user_sequence(user_id)
    current_time = datetime.now()
    elapsed_seconds = int((current_time - GLOBAL_START_TIME).total_seconds())
    
    total_duration = 0
    current_video = None
    offset = 0
    for video_name in sequence:
        duration = get_video_duration(user_id, video_name)
        if elapsed_seconds < total_duration + duration:
            current_video = video_name
            offset = elapsed_seconds - total_duration
            break
        total_duration += duration
    
    if not current_video:
        elapsed_seconds = elapsed_seconds % total_duration if total_duration > 0 else 0
        total_duration = 0
        for video_name in sequence:
            duration = get_video_duration(user_id, video_name)
            if elapsed_seconds < total_duration + duration:
                current_video = video_name
                offset = elapsed_seconds - total_duration
                break
            total_duration += duration
    
    offset = max(0, offset)
    video_path = os.path.join(STATIC_DIR, "videos", user_id, f"{current_video}.mp4")
    video_url = f"/static/videos/{user_id}/{current_video}.mp4"
    
    # Ensure the video directory and file exist
    os.makedirs(os.path.dirname(video_path), exist_ok=True)
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail=f"Video {current_video}.mp4 not found at {video_path}")
    
    return {
        "playlist_url": video_url,
        "offset": offset,
        "current_video": current_video
    }

@app.get("/debug/db")
async def debug_db(token: str = Depends(oauth2_scheme)):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, sequence FROM users")
    users = cursor.fetchall()
    cursor.execute("SELECT * FROM videos")
    videos = cursor.fetchall()
    conn.close()
    return {"users": users, "videos": videos}

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if not os.path.exists(index_path):
        return HTMLResponse(content="<h1>Index file not found</h1>", status_code=404)
    with open(index_path, "r") as f:
        return f.read()

if __name__ == "__main__":
    init_db()
    uvicorn.run(app, host="0.0.0.0", port=3333)
