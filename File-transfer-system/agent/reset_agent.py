
import os
import yaml

# Detect script directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.yaml")

if not os.path.exists(CONFIG_FILE):
    print(f"Error: {CONFIG_FILE} not found.")
    exit(1)

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = yaml.safe_load(f) or {}

print(f"Current Agent UUID: {config.get('agent_uuid')}")
print("Resetting identity...")

config["agent_uuid"] = ""
config["agent_token"] = ""

with open(CONFIG_FILE, "w", encoding="utf-8") as f:
    yaml.safe_dump(config, f, sort_keys=False)

print("Identity cleared. The agent will re-register on next start.")
