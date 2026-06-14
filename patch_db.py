import pymysql
conn = pymysql.connect(host='localhost', user='root', password='List@123', database='central_multitenant')
cur = conn.cursor()

# 1. Add columns to users
for col, t in [('password_hash','VARCHAR(255)'),('is_active','BOOLEAN DEFAULT 1'),('last_login_at','DATETIME'),('updated_at','DATETIME')]:
    try: cur.execute(f"ALTER TABLE users ADD COLUMN {col} {t}")
    except Exception: pass

# 2. Add columns to organizations
for col, t in [('is_active','BOOLEAN DEFAULT 1'),('updated_at','DATETIME')]:
    try: cur.execute(f"ALTER TABLE organizations ADD COLUMN {col} {t}")
    except Exception: pass

# 3. Dynamically scan and alter user/org ID columns in other tables (BIGINT -> VARCHAR(100))
cur.execute("SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH, IS_NULLABLE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='central_multitenant' AND COLUMN_NAME IN ('user_id','organization_id','created_by','acknowledged_by','entity_id')")
for t_name, c_name, d_type, length, is_null in cur.fetchall():
    if t_name in ('users','organizations') and c_name in ('id','name','username','email'): continue
    if d_type.lower() in ('varchar','char') and length and length >= 100: continue
    try: cur.execute(f"ALTER TABLE {t_name} MODIFY COLUMN {c_name} VARCHAR(100) {'NULL' if is_null=='YES' else 'NOT NULL'}")
    except Exception as e: print(f"Err altering {t_name}.{c_name}: {e}")

# 4. Populate values
cur.execute("UPDATE users SET password_hash=COALESCE(password_hash, password), is_active=(status='active'), last_login_at=COALESCE(last_login_at, last_login), updated_at=COALESCE(updated_at, created_at, NOW())")
cur.execute("UPDATE organizations SET is_active=(status='active'), updated_at=COALESCE(updated_at, created_at, NOW())")

# 5. Recreate triggers
for name in ['tg_users_insert','tg_users_update','tg_organizations_insert','tg_organizations_update']:
    cur.execute(f"DROP TRIGGER IF EXISTS {name}")

cur.execute("""CREATE TRIGGER tg_users_insert BEFORE INSERT ON users FOR EACH ROW BEGIN
    IF NEW.password IS NOT NULL AND NEW.password_hash IS NULL THEN SET NEW.password_hash = NEW.password;
    ELSEIF NEW.password_hash IS NOT NULL AND NEW.password IS NULL THEN SET NEW.password = NEW.password_hash; END IF;
    IF NEW.status IS NOT NULL AND NEW.is_active IS NULL THEN SET NEW.is_active = (NEW.status = 'active');
    ELSEIF NEW.is_active IS NOT NULL AND NEW.status IS NULL THEN SET NEW.status = IF(NEW.is_active, 'active', 'inactive'); END IF;
    IF NEW.last_login IS NOT NULL AND NEW.last_login_at IS NULL THEN SET NEW.last_login_at = NEW.last_login;
    ELSEIF NEW.last_login_at IS NOT NULL AND NEW.last_login IS NULL THEN SET NEW.last_login = NEW.last_login_at; END IF;
    IF NEW.updated_at IS NULL THEN SET NEW.updated_at = COALESCE(NEW.created_at, NOW()); END IF;
END""")

cur.execute("""CREATE TRIGGER tg_users_update BEFORE UPDATE ON users FOR EACH ROW BEGIN
    IF NEW.password <=> OLD.password AND NOT (NEW.password_hash <=> OLD.password_hash) THEN SET NEW.password = NEW.password_hash;
    ELSEIF NEW.password_hash <=> OLD.password_hash AND NOT (NEW.password <=> OLD.password) THEN SET NEW.password_hash = NEW.password; END IF;
    IF NEW.status <=> OLD.status AND NOT (NEW.is_active <=> OLD.is_active) THEN SET NEW.status = IF(NEW.is_active, 'active', 'inactive');
    ELSEIF NEW.is_active <=> OLD.is_active AND NOT (NEW.status <=> OLD.status) THEN SET NEW.is_active = (NEW.status = 'active'); END IF;
    IF NEW.last_login <=> OLD.last_login AND NOT (NEW.last_login_at <=> OLD.last_login_at) THEN SET NEW.last_login = NEW.last_login_at;
    ELSEIF NEW.last_login_at <=> OLD.last_login_at AND NOT (NEW.last_login <=> OLD.last_login) THEN SET NEW.last_login_at = NEW.last_login; END IF;
    SET NEW.updated_at = CURRENT_TIMESTAMP;
END""")

cur.execute("""CREATE TRIGGER tg_organizations_insert BEFORE INSERT ON organizations FOR EACH ROW BEGIN
    IF NEW.status IS NOT NULL AND NEW.is_active IS NULL THEN SET NEW.is_active = (NEW.status = 'active');
    ELSEIF NEW.is_active IS NOT NULL AND NEW.status IS NULL THEN SET NEW.status = IF(NEW.is_active, 'active', 'disabled'); END IF;
    IF NEW.updated_at IS NULL THEN SET NEW.updated_at = COALESCE(NEW.created_at, NOW()); END IF;
END""")

cur.execute("""CREATE TRIGGER tg_organizations_update BEFORE UPDATE ON organizations FOR EACH ROW BEGIN
    IF NEW.status <=> OLD.status AND NOT (NEW.is_active <=> OLD.is_active) THEN SET NEW.status = IF(NEW.is_active, 'active', 'disabled');
    ELSEIF NEW.is_active <=> OLD.is_active AND NOT (NEW.status <=> OLD.status) THEN SET NEW.is_active = (NEW.status = 'active'); END IF;
    SET NEW.updated_at = CURRENT_TIMESTAMP;
END""")

conn.commit()
conn.close()
print("=== DATABASE SCHEMA COMPATIBILITY PATCH COMPLETED ===")
