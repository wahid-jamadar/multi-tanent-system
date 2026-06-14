#!/bin/bash
set -e

echo "=================================================="
echo " BatchHost-Pro Agent RPM Builder (Oracle Linux 9) "
echo "=================================================="

# 1. Install prerequisites
echo "[1/4] Installing dependencies (rpm-build, python3, pip, tar)..."
sudo dnf install -y rpm-build python3 python3-pip tar

# 2. Setup workspace
echo "[2/4] Setting up RPM build directory..."
mkdir -p ~/rpmbuild/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

# 3. Create the source archive
echo "[3/4] Creating source tarball..."
mkdir -p batchhost-agent-2.0
cp agent_runtime.py batchhost-agent-2.0/
cp batchhost-agent.service batchhost-agent-2.0/
tar -czf batchhost-agent-2.0.tar.gz batchhost-agent-2.0/
cp batchhost-agent-2.0.tar.gz ~/rpmbuild/SOURCES/
cp batchhost-agent.spec ~/rpmbuild/SPECS/

# 4. Build the RPM
echo "[4/4] Building the RPM..."
rpmbuild -ba ~/rpmbuild/SPECS/batchhost-agent.spec

echo ""
echo "=================================================="
echo " BUILD SUCCESSFUL!"
echo " Your RPM package is located at:"
ls -l ~/rpmbuild/RPMS/x86_64/batchhost-agent-2.0-1*.rpm
echo ""
echo " You can install it on any Oracle Linux 9 server using:"
echo " sudo rpm -ivh ~/rpmbuild/RPMS/x86_64/batchhost-agent-2.0-1*.rpm"
echo "=================================================="
