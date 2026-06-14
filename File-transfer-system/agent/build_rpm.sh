#!/bin/bash
set -e

echo "Building FileBridge Agent RPM..."

VERSION="1.5.2"
NAME="filebridge-agent"

mkdir -p ~/rpmbuild/{BUILD,RPMS,SOURCES,SPECS,SRPMS}
rm -rf ~/rpmbuild/SOURCES/${NAME}-${VERSION}
mkdir -p ~/rpmbuild/SOURCES/${NAME}-${VERSION}

cp agent.py filebridge-agent.service config.yaml ~/rpmbuild/SOURCES/${NAME}-${VERSION}/
cd ~/rpmbuild/SOURCES/
tar -czvf ${NAME}-${VERSION}.tar.gz ${NAME}-${VERSION}
rm -rf ${NAME}-${VERSION}

cd -
cp filebridge-agent.spec ~/rpmbuild/SPECS/

rpmbuild -ba ~/rpmbuild/SPECS/filebridge-agent.spec

echo "RPM built successfully at ~/rpmbuild/RPMS/x86_64/"
