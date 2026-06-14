from app import app, db, TransferJob, Agent, Server


def list_all_recent():
    with app.app_context():
        jobs = TransferJob.query.order_by(TransferJob.created_at.desc()).limit(10).all()
        for j in jobs:
            agent = db.session.get(Agent, j.assigned_agent_id) if j.assigned_agent_id else None
            server = agent.server if agent else None
            print(f"UUID: {j.job_uuid} | Type: {j.job_type} | Status: {j.status} | AgentServer: {server.name if server else 'None'}")
            print(f"  Src: {j.source_path} (ServerID: {j.source_server_id})")
            print(f"  Dst: {j.destination_path} (ServerID: {j.destination_server_id})")

if __name__ == "__main__":
    list_all_recent()
