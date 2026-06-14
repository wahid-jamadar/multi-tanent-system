import os
import pymysql

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'List@123',
    'port': 3306
}

db_dir = os.path.dirname(os.path.abspath(__file__))
script_path = os.path.join(db_dir, "script.sql")

print(f"Reading SQL script from: {script_path}")
if not os.path.exists(script_path):
    print("Error: script.sql not found.")
    exit(1)

with open(script_path, "r", encoding="utf-8") as f:
    sql_content = f.read()

# Connect to MySQL (no database specified initially because the script creates/uses it)
print("Connecting to MySQL...")
conn = pymysql.connect(**DB_CONFIG)
try:
    cursor = conn.cursor()
    # Disable foreign key checks while applying schema just in case
    cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
    
    # Split queries by semicolon
    statements = sql_content.split(";")
    executed_count = 0
    for stmt in statements:
        stmt = stmt.strip()
        if not stmt:
            continue
        
        # Execute query
        print(f"Executing statement:\n{stmt[:100]}...")
        cursor.execute(stmt)
        executed_count += 1
        
    cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
    conn.commit()
    print(f"Successfully executed {executed_count} statements.")
except Exception as e:
    conn.rollback()
    print(f"Error executing SQL: {e}")
    raise
finally:
    conn.close()
