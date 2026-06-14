import json
import pymysql
import os
from datetime import datetime

print("=== STARTING SHARED MYSQL SEEDING UTILITY ===")

# Paths to the JSON files
portal_dir = os.path.dirname(os.path.abspath(__file__))
base_dir = os.path.dirname(portal_dir)
orgs_file = os.path.join(base_dir, "BatchHost-Pro", "data", "organizations.json")
users_file = os.path.join(base_dir, "BatchHost-Pro", "data", "users.json")

# Connect to the centralized MySQL database on port 3306 and create DB/tables if needed
try:
    conn = pymysql.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", "List@123"),
        port=int(os.environ.get("DB_PORT", 3306))
    )
    cursor = conn.cursor()
    
    print("Creating central_multitenant database if not exists...")
    cursor.execute("CREATE DATABASE IF NOT EXISTS central_multitenant CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;")
    cursor.execute("USE central_multitenant;")
    
    print("Creating organizations table if not exists...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS organizations (
            id VARCHAR(100) PRIMARY KEY,
            name VARCHAR(150) NOT NULL UNIQUE,
            status VARCHAR(50) NOT NULL DEFAULT 'active',
            is_active BOOLEAN DEFAULT TRUE,
            logo VARCHAR(255) NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """)

    # Create organizations triggers
    cursor.execute("DROP TRIGGER IF EXISTS tg_organizations_insert;")
    cursor.execute("""
        CREATE TRIGGER tg_organizations_insert BEFORE INSERT ON organizations
        FOR EACH ROW
        BEGIN
            -- Sync status and is_active
            IF NEW.status IS NOT NULL AND NEW.is_active IS NULL THEN
                SET NEW.is_active = IF(NEW.status = 'active', 1, 0);
            ELSEIF NEW.is_active IS NOT NULL AND NEW.status IS NULL THEN
                SET NEW.status = IF(NEW.is_active = 1, 'active', 'disabled');
            END IF;

            -- Sync updated_at
            IF NEW.updated_at IS NULL THEN
                SET NEW.updated_at = COALESCE(NEW.created_at, NOW());
            END IF;
        END;
    """)

    cursor.execute("DROP TRIGGER IF EXISTS tg_organizations_update;")
    cursor.execute("""
        CREATE TRIGGER tg_organizations_update BEFORE UPDATE ON organizations
        FOR EACH ROW
        BEGIN
            -- Sync status and is_active
            IF NEW.status <=> OLD.status AND NOT (NEW.is_active <=> OLD.is_active) THEN
                SET NEW.status = IF(NEW.is_active = 1, 'active', 'disabled');
            ELSEIF NEW.is_active <=> OLD.is_active AND NOT (NEW.status <=> OLD.status) THEN
                SET NEW.is_active = IF(NEW.status = 'active', 1, 0);
            END IF;

            -- Set updated_at
            SET NEW.updated_at = CURRENT_TIMESTAMP;
        END;
    """)
    
    print("Creating users table if not exists...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id VARCHAR(100) PRIMARY KEY,
            username VARCHAR(100) NOT NULL UNIQUE,
            email VARCHAR(255) NOT NULL UNIQUE,
            password VARCHAR(255) NOT NULL,
            password_hash VARCHAR(255) NULL,
            is_active BOOLEAN DEFAULT TRUE,
            batchhost_role VARCHAR(50) NOT NULL,
            filebridge_role VARCHAR(50) NOT NULL,
            organization_id VARCHAR(100) NOT NULL,
            status VARCHAR(50) NOT NULL DEFAULT 'active',
            last_login DATETIME NULL,
            last_login_at DATETIME NULL,
            previous_login DATETIME NULL,
            total_logins INT DEFAULT 0,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NULL,
            FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """)

    # Create the triggers if they don't exist
    cursor.execute("DROP TRIGGER IF EXISTS tg_users_insert;")
    cursor.execute("""
        CREATE TRIGGER tg_users_insert BEFORE INSERT ON users
        FOR EACH ROW
        BEGIN
            -- Sync password and password_hash
            IF NEW.password IS NOT NULL AND NEW.password_hash IS NULL THEN
                SET NEW.password_hash = NEW.password;
            ELSEIF NEW.password_hash IS NOT NULL AND NEW.password IS NULL THEN
                SET NEW.password = NEW.password_hash;
            END IF;

            -- Sync status and is_active
            IF NEW.status IS NOT NULL AND NEW.is_active IS NULL THEN
                SET NEW.is_active = IF(NEW.status = 'active', 1, 0);
            ELSEIF NEW.is_active IS NOT NULL AND NEW.status IS NULL THEN
                SET NEW.status = IF(NEW.is_active = 1, 'active', 'inactive');
            END IF;

            -- Sync last_login and last_login_at
            IF NEW.last_login IS NOT NULL AND NEW.last_login_at IS NULL THEN
                SET NEW.last_login_at = NEW.last_login;
            ELSEIF NEW.last_login_at IS NOT NULL AND NEW.last_login IS NULL THEN
                SET NEW.last_login = NEW.last_login_at;
            END IF;

            -- Sync updated_at
            IF NEW.updated_at IS NULL THEN
                SET NEW.updated_at = COALESCE(NEW.created_at, NOW());
            END IF;
        END;
    """)

    cursor.execute("DROP TRIGGER IF EXISTS tg_users_update;")
    cursor.execute("""
        CREATE TRIGGER tg_users_update BEFORE UPDATE ON users
        FOR EACH ROW
        BEGIN
            -- Sync password and password_hash
            IF NEW.password <=> OLD.password AND NOT (NEW.password_hash <=> OLD.password_hash) THEN
                SET NEW.password = NEW.password_hash;
            ELSEIF NEW.password_hash <=> OLD.password_hash AND NOT (NEW.password <=> OLD.password) THEN
                SET NEW.password_hash = NEW.password;
            END IF;

            -- Sync status and is_active
            IF NEW.status <=> OLD.status AND NOT (NEW.is_active <=> OLD.is_active) THEN
                SET NEW.status = IF(NEW.is_active = 1, 'active', 'inactive');
            ELSEIF NEW.is_active <=> OLD.is_active AND NOT (NEW.status <=> OLD.status) THEN
                SET NEW.is_active = IF(NEW.status = 'active', 1, 0);
            END IF;

            -- Sync last_login and last_login_at
            IF NEW.last_login <=> OLD.last_login AND NOT (NEW.last_login_at <=> OLD.last_login_at) THEN
                SET NEW.last_login = NEW.last_login_at;
            ELSEIF NEW.last_login_at <=> OLD.last_login_at AND NOT (NEW.last_login <=> OLD.last_login) THEN
                SET NEW.last_login_at = NEW.last_login;
            END IF;

            -- Set updated_at
            SET NEW.updated_at = CURRENT_TIMESTAMP;
        END;
    """)

    
    # 1. Seed Organizations
    print("Loading organizations.json...")
    if os.path.exists(orgs_file):
        with open(orgs_file, 'r') as f:
            orgs = json.load(f)
            
        print(f"Loaded {len(orgs)} organizations. Seeding into MySQL...")
        for org in orgs:
            # Parse created_at ISO string
            created_at = org.get('created_at')
            if created_at:
                try:
                    created_at = datetime.fromisoformat(created_at)
                except Exception:
                    created_at = datetime.now()
            else:
                created_at = datetime.now()
                
            cursor.execute("""
                INSERT INTO organizations (id, name, status, logo, created_at)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE name=%s, status=%s, logo=%s;
            """, (
                org['id'],
                org['name'],
                org.get('status', 'active'),
                org.get('logo'),
                created_at,
                org['name'],
                org.get('status', 'active'),
                org.get('logo')
            ))
        print("Organizations seeded successfully.")
    else:
        print(f"WARNING: organizations.json not found at {orgs_file}")
        
    # 2. Seed Users
    print("Loading users.json...")
    if os.path.exists(users_file):
        with open(users_file, 'r') as f:
            users = json.load(f)
            
        print(f"Loaded {len(users)} users. Seeding into MySQL...")
        for user in users:
            # Parse created_at, last_login, previous_login
            created_at = user.get('created_at')
            created_at = datetime.fromisoformat(created_at) if created_at else datetime.now()
            
            last_login = user.get('last_login')
            if last_login:
                try:
                    last_login = datetime.fromisoformat(last_login)
                except Exception:
                    last_login = None
            else:
                last_login = None
                
            previous_login = user.get('previous_login')
            if previous_login:
                try:
                    previous_login = datetime.fromisoformat(previous_login)
                except Exception:
                    previous_login = None
            else:
                previous_login = None
                
            cursor.execute("""
                INSERT INTO users (id, username, email, password, batchhost_role, filebridge_role, organization_id, status, last_login, previous_login, total_logins, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE username=%s, email=%s, password=%s, batchhost_role=%s, filebridge_role=%s, organization_id=%s, status=%s, last_login=%s, previous_login=%s, total_logins=%s;
            """, (
                user['id'],
                user['username'],
                user['email'],
                user['password'],
                user.get('batchhost_role', user.get('role', 'viewer')),
                user.get('filebridge_role', user.get('role', 'viewer')),
                user['organization_id'],
                user.get('status', 'active'),
                last_login,
                previous_login,
                user.get('total_logins', 0),
                created_at,
                # On duplicate key update values:
                user['username'],
                user['email'],
                user['password'],
                user.get('batchhost_role', user.get('role', 'viewer')),
                user.get('filebridge_role', user.get('role', 'viewer')),
                user['organization_id'],
                user.get('status', 'active'),
                last_login,
                previous_login,
                user.get('total_logins', 0)
            ))
        print("Users seeded successfully.")
    else:
        print(f"WARNING: users.json not found at {users_file}")
        
    conn.commit()
    conn.close()
    print("=== SEEDING COMPLETE ===")
except Exception as e:
    print(f"Seeding failed: {e}")
