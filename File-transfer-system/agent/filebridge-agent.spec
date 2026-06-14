%global debug_package %{nil}
%global _build_id_links none
Name:           filebridge-agent
Version:        1.5.2
Release:        1%{?dist}
Summary:        FileBridge Agent Runtime
License:        Proprietary
URL:            https://filebridge.local
Source0:        %{name}-%{version}.tar.gz

%description
FileBridge distributed file synchronization and monitoring agent.
This package installs the agent to run continuously in the background using systemd.

%prep
%setup -q

%build
# Use venv to install pyinstaller and build the single binary
python3 -m venv venv
source venv/bin/activate
pip install pyinstaller psutil requests urllib3 pyyaml
pyinstaller --onefile --name filebridge-agent agent.py
deactivate

%install
rm -rf %{buildroot}
mkdir -p %{buildroot}/root/filebridge-agent
mkdir -p %{buildroot}/etc/systemd/system

install -m 755 dist/filebridge-agent %{buildroot}/root/filebridge-agent/filebridge-agent
install -m 644 filebridge-agent.service %{buildroot}/etc/systemd/system/filebridge-agent.service
install -m 644 config.yaml %{buildroot}/root/filebridge-agent/config.yaml

%clean
rm -rf %{buildroot}

%files
%defattr(-,root,root,-)
%attr(755, root, root) /root/filebridge-agent/filebridge-agent
/root/filebridge-agent/config.yaml
/etc/systemd/system/filebridge-agent.service
%dir /root/filebridge-agent

%post
chcon -t bin_t /root/filebridge-agent/filebridge-agent || true
systemctl daemon-reload
systemctl enable filebridge-agent.service
systemctl restart filebridge-agent.service

%preun
if [ $1 -eq 0 ] ; then
    systemctl stop filebridge-agent.service
    systemctl disable filebridge-agent.service
fi

%postun
if [ $1 -eq 0 ] ; then
    systemctl daemon-reload
fi
