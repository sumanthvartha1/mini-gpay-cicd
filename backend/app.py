import os
import json
import time
import psycopg2
import redis
from flask import Flask, jsonify, request
from psycopg2.extras import RealDictCursor

# ============================================
# SETUP — connect to services using Docker DNS
# ============================================
# These environment variables come from docker-compose.yml
# Docker DNS resolves "postgres" and "redis" to the correct container IPs

app = Flask(__name__)

def get_db():
    """Create a new database connection.
    DB_HOST is 'postgres' — the service name in docker-compose.yml.
    Docker DNS resolves this to the PostgreSQL container's IP."""
    return psycopg2.connect(
        host=os.environ["DB_HOST"],       # "postgres" — resolved by Docker DNS
        database=os.environ["DB_NAME"],   # "payments"
        user=os.environ["DB_USER"],       # "admin"
        password=os.environ["DB_PASSWORD"], # "password123"
        cursor_factory=RealDictCursor     # returns rows as dictionaries, not tuples
    )

def get_cache():
    """Connect to Redis cache.
    REDIS_HOST is 'redis' — the service name in docker-compose.yml."""
    return redis.Redis(
        host=os.environ["REDIS_HOST"],  # "redis" — resolved by Docker DNS
        port=6379,                       # default Redis port
        decode_responses=True            # return strings, not bytes
    )

# ============================================
# WAIT FOR DATABASE — retry until PostgreSQL is ready
# ============================================
# Even with healthchecks, we add retry logic as a safety net

def wait_for_db():
    """Keep trying to connect to PostgreSQL until it's ready."""
    for i in range(30):  # try 30 times
        try:
            conn = get_db()
            conn.close()
            print("Database connected!")
            return
        except Exception:
            print(f"Waiting for database... attempt {i+1}")
            time.sleep(2)  # wait 2 seconds before retrying
    print("Could not connect to database!")

# ============================================
# API ROUTES — each one handles a different action
# ============================================

# ROUTE 1: Get all users
@app.route("/api/users")
def get_users():
    """Returns list of all users. 
    The frontend calls this to show the user list."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, name, phone, balance FROM users ORDER BY name")
    users = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify(users)

# ROUTE 2: Get one user's balance
@app.route("/api/balance/<int:user_id>")
def get_balance(user_id):
    """Returns a single user's balance.
    First checks Redis cache. If not cached, queries PostgreSQL.
    
    <int:user_id> means Flask extracts the number from the URL.
    /api/balance/1 → user_id = 1"""
    
    cache = get_cache()
    cache_key = f"balance:{user_id}"
    
    # Step 1: Check Redis first (fast — 1ms)
    cached = cache.get(cache_key)
    if cached:
        print(f"Cache HIT for user {user_id}")
        return jsonify({"balance": cached, "source": "cache"})
    
    # Step 2: Not in cache — query PostgreSQL (slower — 50ms)
    print(f"Cache MISS for user {user_id} — querying database")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT name, balance FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    
    if not user:
        return jsonify({"error": "User not found"}), 404
    
    # Step 3: Save to Redis for next time (cache for 60 seconds)
    cache.set(cache_key, str(user["balance"]), ex=60)
    
    return jsonify({
        "name": user["name"],
        "balance": str(user["balance"]),
        "source": "database"
    })

# ROUTE 3: Send money
@app.route("/api/send", methods=["POST"])
def send_money():
    """Transfer money from one user to another.
    
    POST means the frontend sends data TO the backend (not just reading).
    The data comes as JSON in the request body:
    { "sender_id": 1, "receiver_id": 2, "amount": 500 }"""
    
    data = request.json  # read the JSON body from the request
    sender_id = data["sender_id"]
    receiver_id = data["receiver_id"]
    amount = float(data["amount"])
    
    # Validation — check for bad input
    if amount <= 0:
        return jsonify({"error": "Amount must be greater than 0"}), 400
    if sender_id == receiver_id:
        return jsonify({"error": "Cannot send money to yourself"}), 400
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        # Check sender has enough balance
        cur.execute("SELECT balance FROM users WHERE id = %s", (sender_id,))
        sender = cur.fetchone()
        
        if not sender:
            return jsonify({"error": "Sender not found"}), 404
        if sender["balance"] < amount:
            return jsonify({"error": "Insufficient balance"}), 400
        
        # Deduct from sender
        cur.execute(
            "UPDATE users SET balance = balance - %s WHERE id = %s",
            (amount, sender_id)
        )
        
        # Add to receiver
        cur.execute(
            "UPDATE users SET balance = balance + %s WHERE id = %s",
            (amount, receiver_id)
        )
        
        # Record the transaction
        cur.execute(
            "INSERT INTO transactions (sender_id, receiver_id, amount) VALUES (%s, %s, %s)",
            (sender_id, receiver_id, amount)
        )
        
        # Commit — save all changes to database at once
        conn.commit()
        
        # Clear cache — balances changed, old cache is wrong now
        cache = get_cache()
        cache.delete(f"balance:{sender_id}")
        cache.delete(f"balance:{receiver_id}")
        
        return jsonify({"message": f"Sent {amount} successfully!"})
    
    except Exception as e:
        conn.rollback()  # undo everything if any step fails
        return jsonify({"error": str(e)}), 500
    finally:
        cur.close()
        conn.close()

# ROUTE 4: Transaction history
@app.route("/api/transactions/<int:user_id>")
def get_transactions(user_id):
    """Returns all transactions for a user — both sent and received."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT t.id, t.amount, t.status, t.created_at,
               s.name as sender_name, r.name as receiver_name
        FROM transactions t
        JOIN users s ON t.sender_id = s.id
        JOIN users r ON t.receiver_id = r.id
        WHERE t.sender_id = %s OR t.receiver_id = %s
        ORDER BY t.created_at DESC
    """, (user_id, user_id))
    transactions = cur.fetchall()
    cur.close()
    conn.close()
    
    # Convert datetime to string for JSON
    result = []
    for t in transactions:
        result.append({
            "id": t["id"],
            "amount": str(t["amount"]),
            "status": t["status"],
            "sender": t["sender_name"],
            "receiver": t["receiver_name"],
            "date": t["created_at"].strftime("%Y-%m-%d %H:%M")
        })
    
    return jsonify(result)

# ROUTE 5: Health check — ECS/Kubernetes uses this to verify the app is alive
@app.route("/api/health")
def health():
    """Simple health check endpoint. Returns 200 if the app is running."""
    return jsonify({"status": "healthy"})

# ============================================
# START THE APP
# ============================================
if __name__ == "__main__":
    wait_for_db()
    app.run(host="0.0.0.0", port=5000)
    # host="0.0.0.0" means accept connections from anywhere (not just localhost)
    # port=5000 means listen on port 5000 inside the container
