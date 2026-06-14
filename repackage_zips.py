import zipfile
import os
import re

# ─── HELPERS ─────────────────────────────────────────────────────────────────

def to_lf(file_path):
    """Read a file and return its content with all CRLF converted to LF.
    Used when packaging files for Linux RPM builds so that Windows line-endings
    never make it into the zip and cause '/bin/bash^M: bad interpreter' errors."""
    with open(file_path, 'rb') as f:
        raw = f.read()
    return raw.replace(b'\r\n', b'\n').replace(b'\r', b'\n')

def add_as_lf(zf, file_path, arcname):
    """Add a file to a ZipFile with LF line endings, regardless of source OS."""
    zf.writestr(arcname, to_lf(file_path))

def get_bootstrap_token(config_path):
    try:
        with open(config_path, "r") as f:
            content = f.read()
            m = re.search(r"bootstrap_token:\s*['\"]?([^'\"\n]+)['\"]?", content)
            if m:
                return m.group(1)
    except Exception as e:
        print(f"  Error reading bootstrap token: {e}")
    return "R52FNdbbPsUXFFU04tWRRN00RfScXpzh1ZvwQf_r_wY" # Default token

def main():
    # ─── BATCHHOST-PRO PACKAGING ──────────────────────────────────────────────
    bh_base_dir = "c:/Amulti-tanent-system/BatchHost-Pro"
    
    # 1. Repack agents.zip (Windows)
    agents_zip_path = os.path.join(bh_base_dir, "agents.zip")
    agents_dir = os.path.join(bh_base_dir, "agents")
    files_for_agents = [
        "agent_runtime.py",
        "batchhost-pro_agent.bat",
        "batchhost-pro_agent.sh",
        "batchhost-agent-service.xml",
        "batchhost-agent-service.exe",
        "batchhost-agent-service.exe.bak",
        "start_agent_hidden.vbs",
        "stop_agent.bat"
    ]

    print("Creating agents.zip (BatchHost-Pro Windows)...")
    if os.path.exists(agents_zip_path):
        os.remove(agents_zip_path)
        
    with zipfile.ZipFile(agents_zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("agents/", "")
        for f in files_for_agents:
            full_path = os.path.join(agents_dir, f)
            if os.path.exists(full_path):
                z.write(full_path, os.path.join("agents", f))
                print(f"  Added to agents.zip: agents/{f}")
            else:
                print(f"  WARNING: File not found: {full_path}")
                
    # 2. Repack agent-rpm-build.zip (BatchHost-Pro Linux)
    rpm_zip_path = os.path.join(bh_base_dir, "agent-rpm-build.zip")
    rpm_dir = os.path.join(bh_base_dir, "agent-rpm-build")
    files_for_rpm = [
        "agent_runtime.py",
        "batchhost-agent.service",
        "batchhost-agent.spec",
        "build_rpm.sh"
    ]
    
    print("Creating agent-rpm-build.zip (BatchHost-Pro Linux)...")
    if os.path.exists(rpm_zip_path):
        os.remove(rpm_zip_path)
        
    with zipfile.ZipFile(rpm_zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files_for_rpm:
            full_path = os.path.join(rpm_dir, f)
            if os.path.exists(full_path):
                add_as_lf(z, full_path, f)  # Always LF — no CRLF on Linux
                print(f"  Added to agent-rpm-build.zip: {f} (LF)")
            else:
                print(f"  WARNING: File not found: {full_path}")

    # ─── FILEBRIDGE PACKAGING ─────────────────────────────────────────────────
    fb_base_dir = "c:/Amulti-tanent-system/File-transfer-system/agent"
    
    # 3. Repack FileBridgeAgent_DEPLOY.zip (FileBridge Windows)
    fb_deploy_zip_path = os.path.join(fb_base_dir, "FileBridgeAgent_DEPLOY.zip")
    print("Creating FileBridgeAgent_DEPLOY.zip (FileBridge Windows)...")
    if os.path.exists(fb_deploy_zip_path):
        os.remove(fb_deploy_zip_path)
        
    with zipfile.ZipFile(fb_deploy_zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        # File mapping to place them in the zip root
        fb_win_files = [
            ("dist/FileBridgeAgent.exe", "FileBridgeAgent.exe"),
            ("FileBridgeAgentService.exe", "FileBridgeAgentService.exe"),
            ("FileBridgeAgentService.xml", "FileBridgeAgentService.xml"),
            ("config.yaml", "config.yaml"),
            ("manage_service.ps1", "manage_service.ps1"),
            ("README_SERVICE.md", "README_SERVICE.md")
        ]
        
        for src_rel, dst_name in fb_win_files:
            full_path = os.path.join(fb_base_dir, src_rel)
            if os.path.exists(full_path):
                z.write(full_path, dst_name)
                print(f"  Added to FileBridgeAgent_DEPLOY.zip: {dst_name}")
            else:
                print(f"  WARNING: File not found: {full_path}")
        
        # Add empty logs directory
        z.writestr("logs/", "")
        print("  Added to FileBridgeAgent_DEPLOY.zip: logs/")

    # 4. Repack filebridge-agent-rpm-build.zip (FileBridge Linux)
    fb_rpm_zip_path = os.path.join(fb_base_dir, "filebridge-agent-rpm-build.zip")
    print("Creating filebridge-agent-rpm-build.zip (FileBridge Linux)...")
    if os.path.exists(fb_rpm_zip_path):
        os.remove(fb_rpm_zip_path)
        
    token = get_bootstrap_token(os.path.join(fb_base_dir, "config.yaml"))
    
    # Read config_linux.yaml and replace the bootstrap token with the actual one
    config_linux_path = os.path.join(fb_base_dir, "config_linux.yaml")
    if os.path.exists(config_linux_path):
        with open(config_linux_path, "r") as f:
            linux_config_content = f.read()
        linux_config_content = linux_config_content.replace("CHANGE-ME-BOOTSTRAP-TOKEN", token)
        # Force default base path to / and machine name
        # We also want to replace CHANGE-ME-HOSTNAME with a default of empty string or let post install handle it
        linux_config_content = linux_config_content.replace("CHANGE-ME-HOSTNAME", "")
    else:
        print("  WARNING: config_linux.yaml not found!")
        linux_config_content = ""

    with zipfile.ZipFile(fb_rpm_zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        if linux_config_content:
            z.writestr("config.yaml", linux_config_content)
            print("  Added to filebridge-agent-rpm-build.zip: config.yaml (customized)")
            
        fb_rpm_files = [
            "agent.py",
            "filebridge-agent.service",
            "filebridge-agent.spec",
            "build_rpm.sh"
        ]
        for f in fb_rpm_files:
            full_path = os.path.join(fb_base_dir, f)
            if os.path.exists(full_path):
                add_as_lf(z, full_path, f)  # Always LF — no CRLF on Linux
                print(f"  Added to filebridge-agent-rpm-build.zip: {f} (LF)")
            else:
                print(f"  WARNING: File not found: {full_path}")
                
    print("=== REPACKAGING COMPLETE ===")

if __name__ == "__main__":
    main()
