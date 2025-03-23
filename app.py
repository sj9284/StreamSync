import sqlite3
import json
import os
from fastapi import FastAPI, HTTPException, Depends, Form
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import OAuth2PasswordBearer
from datetime import datetime, time
import uvicorn
from pydantic import BaseModel
import hashlib

app = FastAPI()

# Global start time (00:00 hours)
GLOBAL_START_TIME = datetime.combine(datetime.today(), time(0, 0))

# OAuth2 scheme for token (simplified)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# Initialize database
def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    
    # Drop existing tables to ensure a fresh start (for simplicity)
    cursor.execute("DROP TABLE IF EXISTS users")
    cursor.execute("DROP TABLE IF EXISTS videos")
    
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
    
    # Insert sample data with hashed passwords
    cursor.execute("INSERT OR REPLACE INTO users (user_id, sequence, password) VALUES (?, ?, ?)",
                   ("user1", '["video1", "video2", "video3"]', hashlib.sha256("password1".encode()).hexdigest()))
    cursor.executemany("INSERT OR REPLACE INTO videos (user_id, video_name, duration) VALUES (?, ?, ?)",
                       [("user1", "video1", 45), ("user1", "video2", 50), ("user1", "video3", 55)])
    
    cursor.execute("INSERT OR REPLACE INTO users (user_id, sequence, password) VALUES (?, ?, ?)",
                   ("user2", '["video1", "video2", "video3"]', hashlib.sha256("password2".encode()).hexdigest()))
    cursor.executemany("INSERT OR REPLACE INTO videos (user_id, video_name, duration) VALUES (?, ?, ?)",
                       [("user2", "video1", 45), ("user2", "video2", 50), ("user2", "video3", 55)])
    
    conn.commit()
    conn.close()

# User model for login
class UserLogin(BaseModel):
    username: str
    password: str

def get_user_sequence(user_id: str):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT sequence FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    if not result:
        raise HTTPException(status_code=404, detail="User not found")
    return json.loads(result[0])

def get_video_duration(user_id: str, video_name: str):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT duration FROM videos WHERE user_id = ? AND video_name = ?",
                   (user_id, video_name))
    result = cursor.fetchone()
    conn.close()
    if not result:
        raise HTTPException(status_code=404, detail="Video not found")
    return result[0]

def verify_user(username: str, password: str):
    conn = sqlite3.connect("database.db")
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
    video_path = f"static/videos/{user_id}/{current_video}.mp4"
    if not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail=f"Video {current_video}.mp4 not found")
    
    return {
        "playlist_url": f"/static/videos/{user_id}/{current_video}.mp4",
        "offset": offset,
        "current_video": current_video
    }

@app.get("/static/{path:path}")
async def serve_static(path: str):
    file_path = os.path.join("static", path)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)

@app.get("/debug/db")
async def debug_db(token: str = Depends(oauth2_scheme)):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, sequence FROM users")
    users = cursor.fetchall()
    cursor.execute("SELECT * FROM videos")
    videos = cursor.fetchall()
    conn.close()
    return {"users": users, "videos": videos}

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    with open("static/index.html", "r") as f:
        return f.read()

if __name__ == "__main__":
    init_db()
    uvicorn.run(app, host="0.0.0.0", port=3333)