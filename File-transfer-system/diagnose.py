import os
import sys
import json
import argparse
from datetime import datetime

# Initialize Flask App Context
try:
    from app import app, db, Agent, Server, AuditLog, TransferJob, SystemLog, SyncRule, JobEvent
    from sqlalchemy import inspect
except ImportError as e:
    print(f"Error importing Flask application or database models: {e}")
    sys.exit(1)

def print_header(title):
    print("\n" + "=" * 60)
    print(f" {title.upper()} ".center(60, " "))
    print("=" * 60)

def print_separator():
    print("-" * 60)

# 1. DB Final & Agent Inspection (from check_db_final.py, check_agents.py, inspect_job_debug.py)
def action_agents_overview():
    print_header("Agent & DB Status Overview")
    with app.app_context():
        agents = Agent.query.all()
        print(f"Total Agents in DB: {len(agents)}\n")
        
        for agent in agents:
            server = db.session.get(Server, agent.server_id) if agent.server_id else None
            print(f"Agent Name   : {agent.agent_name or 'N/A'}")
            print(f"Agent UUID   : {agent.agent_uuid}")
            print(f"Agent ID     : {agent.id}")
            print(f"Status       : {agent.status.upper()}")
            print(f"Hostname     : {server.hostname if server else 'N/A'}")
            print(f"Server Name  : {server.name if server else 'N/A'}")
            print(f"Version      : {agent.version or 'N/A'}")
            print(f"Last Heartbeat: {agent.last_heartbeat_at}")
            print_separator()

# 2. System Log / Traceback Viewer (from find_traceback.py, check_errors.py, check_schema.py)
def action_view_logs(limit=20, level=None):
    print_header(f"System Logs (Limit: {limit}, Level: {level or 'ANY'})")
    with app.app_context():
        query = SystemLog.query
        if level:
            query = query.filter(SystemLog.level == level)
        logs = query.order_by(SystemLog.id.desc()).limit(limit).all()
        
        if not logs:
            print("No matching logs found.")
            return
            
        for l in reversed(logs):
            print(f"--- [{l.created_at}] [{l.level}] {l.message} ---")
            if l.context:
                try:
                    if isinstance(l.context, str):
                        context_data = json.loads(l.context)
                    else:
                        context_data = l.context
                    print(f"Context:\n{json.dumps(context_data, indent=2)}")
                except Exception:
                    print(f"Context: {l.context}")
            print_separator()

def action_inspect_log_schema():
    print_header("SystemLog Table Schema")
    with app.app_context():
        columns = inspect(SystemLog).columns
        for c in columns:
            print(f"  Field: {c.name:<20} | Type: {c.type}")
    print_separator()

# 3. Recent System Activity (from check_activity.py)
def action_recent_activity():
    print_header("Recent System Activity")
    with app.app_context():
        print(">>> RECENT AUDIT LOGS (Last 10):")
        audits = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(10).all()
        for l in audits:
            print(f"[{l.created_at}] Action: {l.action} | {l.details}")
        
        print("\n>>> RECENT TRANSFER JOBS (Last 10):")
        jobs = TransferJob.query.order_by(TransferJob.created_at.desc()).limit(10).all()
        for j in jobs:
            print(f"[{j.created_at}] Type: {j.job_type:<6} | Status: {j.status:<8} | Path: {j.source_path} -> {j.destination_path}")
    print_separator()

# 4. Job & Payload Inspection (from check_job.py, check_list_job.py, inspect_jobs.py, inspect_failed_jobs.py, inspect_list_payloads.py)
def action_inspect_recent_jobs(only_failed=False):
    title = "Last 5 Failed Jobs" if only_failed else "Last 5 Jobs & Event Timeline"
    print_header(title)
    with app.app_context():
        query = TransferJob.query
        if only_failed:
            query = query.filter_by(status='failed')
        jobs = query.order_by(TransferJob.created_at.desc()).limit(5).all()
        
        if not jobs:
            print("No jobs found matching criteria.")
            return
            
        for j in jobs:
            agent = db.session.get(Agent, j.assigned_agent_id) if j.assigned_agent_id else None
            server = agent.server if agent else None
            print(f"\nJob UUID   : {j.job_uuid}")
            print(f"Type       : {j.job_type} | Status: {j.status}")
            print(f"Agent Info : {agent.agent_name if agent else 'None'} (Server: {server.name if server else 'None'})")
            print(f"Source     : {j.source_path}")
            print(f"Dest       : {j.destination_path}")
            
            events = JobEvent.query.filter_by(job_id=j.id).order_by(JobEvent.created_at.asc()).all()
            if events:
                print("Events Timeline:")
                for e in events:
                    print(f"  - [{e.created_at}] {e.event_type}: {e.message}")
            else:
                print("Events Timeline: No events recorded.")
            print_separator()

def action_inspect_list_payloads():
    print_header("Recent List Jobs & Payload Contents")
    with app.app_context():
        jobs = TransferJob.query.filter_by(job_type="list").order_by(TransferJob.created_at.desc()).limit(10).all()
        print(f"Found {len(jobs)} recent list jobs:")
        for j in jobs:
            agent = db.session.get(Agent, j.assigned_agent_id) if j.assigned_agent_id else None
            server = agent.server if agent else None
            server_name = server.name if server else "Unknown"
            print(f"\nJob UUID   : {j.job_uuid} | Server: {server_name} (ID: {j.source_server_id})")
            print(f"Status     : {j.status} | Source Path: {j.source_path}")
            if j.result_payload:
                files = j.result_payload.get("files", [])
                print(f"Total entries in payload: {len(files)}")
                for f in files[:15]:  # Limit output to first 15 for readability
                    print(f"  - {f.get('rel_path') or f.get('name')} | is_dir: {f.get('is_dir')} | size: {f.get('size')} | path: {f.get('path')}")
                if len(files) > 15:
                    print(f"  ... and {len(files) - 15} more files.")
            else:
                print("Result Payload: None present.")
            print_separator()

def action_inspect_specific_job(job_uuid=None):
    if not job_uuid:
        job_uuid = input("Enter the Job UUID to inspect: ").strip()
    if not job_uuid:
        print("Invalid Job UUID.")
        return

    print_header(f"Inspecting Job: {job_uuid}")
    with app.app_context():
        j = TransferJob.query.filter_by(job_uuid=job_uuid).first()
        if not j:
            print("Job not found in database.")
            return
        
        src_server = db.session.get(Server, j.source_server_id) if j.source_server_id else None
        dst_server = db.session.get(Server, j.destination_server_id) if j.destination_server_id else None
        agent = db.session.get(Agent, j.assigned_agent_id) if j.assigned_agent_id else None
        
        print(f"Job UUID   : {j.job_uuid}")
        print(f"Job ID     : {j.id}")
        print(f"Job Type   : {j.job_type}")
        print(f"Status     : {j.status}")
        print(f"Created At : {j.created_at}")
        print(f"Source Server: {src_server.name if src_server else 'None'} (ID={j.source_server_id})")
        print(f"Dest Server  : {dst_server.name if dst_server else 'None'} (ID={j.destination_server_id})")
        print(f"Source Path  : {j.source_path}")
        print(f"Dest Path    : {j.destination_path}")
        
        if agent:
            agent_server = db.session.get(Server, agent.server_id) if agent.server_id else None
            print(f"Assigned Agent: {agent.agent_name} (Server ID={agent.server_id}, Server Name={agent_server.name if agent_server else 'None'})")
        else:
            print("Assigned Agent: None")
            
        events = JobEvent.query.filter_by(job_id=j.id).order_by(JobEvent.created_at.asc()).all()
        if events:
            print("\nChronological Events:")
            for e in events:
                print(f"  [{e.created_at}] {e.event_type}: {e.message}")
        
        if j.result_payload:
            print("\nResult Payload (Truncated):")
            print(json.dumps(j.result_payload, indent=2)[:1000])
            if len(str(j.result_payload)) > 1000:
                print("... [Payload Truncated for display] ...")
    print_separator()

# 5. Sync Rule & Sandbox Inspection (from check_sandbox_logs.py, inspect_rule_summary.py)
def action_inspect_sync_rules():
    print_header("Sync Rules & Status")
    with app.app_context():
        rules = SyncRule.query.all()
        if not rules:
            print("No Sync Rules found.")
            return
            
        for r in rules:
            print(f"Rule ID    : {r.id}")
            print(f"Rule Name  : {r.name}")
            print(f"Status     : {r.status}")
            print(f"Interval   : {r.interval_seconds}s")
            print(f"Last Run At: {r.last_run_at}")
            print(f"Source     : Server {r.source_server_id}:{r.source_path}")
            print(f"Dest       : Server {r.destination_server_id}:{r.destination_path}")
            print_separator()

def action_inspect_rule_summary(rule_id=None):
    with app.app_context():
        if not rule_id:
            # Let the user choose
            rules = SyncRule.query.all()
            if not rules:
                print("No Sync Rules available.")
                return
            print("\nAvailable Sync Rules:")
            for r in rules:
                print(f"  [{r.id}] {r.name} (Status: {r.status})")
            val = input("\nEnter Rule ID to inspect details: ").strip()
            if not val.isdigit():
                print("Invalid ID.")
                return
            rule_id = int(val)
            
        r = db.session.get(SyncRule, rule_id)
        if not r:
            print(f"Sync Rule with ID {rule_id} not found.")
            return
            
        print_header(f"Details for Sync Rule {rule_id}: {r.name}")
        print(f"Status       : {r.status}")
        print(f"Last Run At  : {r.last_run_at}")
        print(f"Last Summary : {r.last_summary}")
        
        if r.last_summary:
            remaining = r.last_summary.get("remaining_changes", [])
            print(f"Total remaining changes: {len(remaining)}")
            
            modified_changes = [c for c in remaining if c.get("type") == "modified"]
            added_changes = [c for c in remaining if c.get("type") == "added"]
            deleted_changes = [c for c in remaining if c.get("type") == "deleted"]
            
            print(f"  - Modified Changes: {len(modified_changes)}")
            print(f"  - Added Changes   : {len(added_changes)}")
            print(f"  - Deleted Changes : {len(deleted_changes)}")
            
            if modified_changes:
                print("\n>>> Sample Modified Change Detail:")
                mc = modified_changes[0]
                print(f"Relative Path: {mc.get('rel_path')}")
                left = mc.get("left")
                right = mc.get("right")
                if left:
                    print(f"  Source details: {left}")
                if right:
                    print(f"  Dest details  : {right}")
        print_separator()

def action_check_sandbox_logs():
    print_header("Sandbox Test Log Analysis")
    with app.app_context():
        logs = SystemLog.query.filter(SystemLog.message.like("%Sandbox Test%")).all()
        print(f"Found {len(logs)} log entries for 'Sandbox Test':")
        for l in logs:
            print(f"[{l.created_at}] {l.level.upper()}: {l.message}")
            if l.context:
                print(f"  Context: {l.context}")
                
        rule = SyncRule.query.filter_by(name="Sandbox Test").first()
        if rule:
            print(f"\nRule Status  : {rule.status}")
            print(f"Last Run At  : {rule.last_run_at}")
            print(f"Last Summary : {rule.last_summary}")
        else:
            print("\nSync Rule 'Sandbox Test' not found in database.")
    print_separator()

# 6. Server Config Inspection (from check_server_config.py)
def action_server_config():
    print_header("Server Configuration Values")
    with app.app_context():
        print(f"AGENT_BOOTSTRAP_TOKEN : '{app.config.get('AGENT_BOOTSTRAP_TOKEN')}'")
        print(f"SECRET_KEY            : '{app.config.get('SECRET_KEY')}'")
        print(f"SQLALCHEMY_DATABASE_URI: '{app.config.get('SQLALCHEMY_DATABASE_URI')}'")
    print_separator()


# Interactive Menu CLI
def run_interactive_menu():
    while True:
        print("\n" + "=== FILEBRIDGE DIAGNOSTIC CONTROL PANEL ===".center(60))
        print("  1. Agent Overview & Status (online/offline)")
        print("  2. Recent Activity Logs & Transfer Jobs")
        print("  3. View Recent Server Logs (Errors/Info/Debug)")
        print("  4. SystemLog Database Schema")
        print("  5. Inspect Sync Rules & Schedules")
        print("  6. Inspect Specific Sync Rule Details (Summaries)")
        print("  7. Recent Transfer Jobs & Chronological Timelines")
        print("  8. Inspect Recent List Job Payloads")
        print("  9. Inspect a Specific Job in Detail (by UUID)")
        print(" 10. Run Sandbox Test Log & Rule Analysis")
        print(" 11. View Bootstrap Token & Server Configs")
        print("  q. Quit")
        print("-" * 60)
        
        choice = input("Select an option (1-11 or q): ").strip().lower()
        if choice == 'q':
            print("Exiting control panel. Goodbye!")
            break
        elif choice == '1':
            action_agents_overview()
        elif choice == '2':
            action_recent_activity()
        elif choice == '3':
            sub_choice = input("Level (E)rrors only, or (A)ll logs? (e/a): ").strip().lower()
            if sub_choice == 'e':
                action_view_logs(limit=10, level="ERROR")
            else:
                action_view_logs(limit=20)
        elif choice == '4':
            action_inspect_log_schema()
        elif choice == '5':
            action_inspect_sync_rules()
        elif choice == '6':
            action_inspect_rule_summary()
        elif choice == '7':
            sub_choice = input("Show (F)ailed jobs only, or (A)ll jobs? (f/a): ").strip().lower()
            if sub_choice == 'f':
                action_inspect_recent_jobs(only_failed=True)
            else:
                action_inspect_recent_jobs(only_failed=False)
        elif choice == '8':
            action_inspect_list_payloads()
        elif choice == '9':
            action_inspect_specific_job()
        elif choice == '10':
            action_check_sandbox_logs()
        elif choice == '11':
            action_server_config()
        else:
            print("Invalid choice, please select a valid option.")
            
        input("\nPress Enter to return to the menu...")

def main():
    parser = argparse.ArgumentParser(description="FileBridge Unified Diagnostic and Inspection Tool")
    parser.add_argument("--interactive", "-i", action="store_true", help="Launch interactive management console")
    parser.add_argument("--agents", action="store_true", help="Show all agents and their online/offline state")
    parser.add_argument("--activity", action="store_true", help="Show recent system logs and job activities")
    parser.add_argument("--errors", action="store_true", help="Show recent ERROR-level logs")
    parser.add_argument("--logs", type=int, nargs="?", const=20, help="Show recent system logs (specify count)")
    parser.add_argument("--schema", action="store_true", help="Show SystemLog table schema")
    parser.add_argument("--rules", action="store_true", help="Show sync rules configuration")
    parser.add_argument("--rule-id", type=int, help="Show remaining changes summary for specified Sync Rule ID")
    parser.add_argument("--failed-jobs", action="store_true", help="Show recently failed transfer jobs with events")
    parser.add_argument("--list-payloads", action="store_true", help="Show payloads of recent list jobs")
    parser.add_argument("--job", type=str, help="Inspect detailed timeline/payload for a specific Job UUID")
    parser.add_argument("--sandbox", action="store_true", help="Analyze Sandbox Test logs and sync rules")
    parser.add_argument("--config", action="store_true", help="Show primary server configuration tokens")

    args = parser.parse_args()

    # If no flags are provided, launch the interactive menu by default
    if not any(vars(args).values()):
        run_interactive_menu()
        return

    if args.interactive:
        run_interactive_menu()
    if args.agents:
        action_agents_overview()
    if args.activity:
        action_recent_activity()
    if args.errors:
        action_view_logs(limit=10, level="ERROR")
    if args.logs:
        action_view_logs(limit=args.logs)
    if args.schema:
        action_inspect_log_schema()
    if args.rules:
        action_inspect_sync_rules()
    if args.rule_id is not None:
        action_inspect_rule_summary(rule_id=args.rule_id)
    if args.failed_jobs:
        action_inspect_recent_jobs(only_failed=True)
    if args.list_payloads:
        action_inspect_list_payloads()
    if args.job:
        action_inspect_specific_job(job_uuid=args.job)
    if args.sandbox:
        action_sandbox_logs()
    if args.config:
        action_server_config()

if __name__ == "__main__":
    main()
