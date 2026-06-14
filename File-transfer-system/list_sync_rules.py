from app import app, db, SyncRule

def list_rules():
    with app.app_context():
        rules = SyncRule.query.all()
        for r in rules:
            print(f"Rule ID: {r.id} | Name: {r.name} | Status: {r.status} | Enabled: {r.is_enabled}")
            print(f"  Direction: {r.direction} | Interval: {r.interval}")
            print(f"  Left Server ID: {r.left_server_id} | Path: {r.left_path}")
            print(f"  Right Server ID: {r.right_server_id} | Path: {r.right_path}")
            print(f"  Last Run: {r.last_run_at}")
            print(f"  Last Summary: {r.last_summary}")
            print("-" * 50)

if __name__ == "__main__":
    list_rules()
