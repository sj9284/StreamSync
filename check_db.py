import sqlite3

conn = sqlite3.connect("database.db")
cursor = conn.cursor()
cursor.execute("SELECT * FROM users")
print("Users:", cursor.fetchall())
cursor.execute("SELECT * FROM videos")
print("Videos:", cursor.fetchall())
conn.close()