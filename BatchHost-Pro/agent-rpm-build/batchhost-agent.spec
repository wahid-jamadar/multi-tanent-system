%global debug_package %{nil}
Name:           batchhost-agent
Version:        2.0
Release:        1%{?dist}
Summary:        BatchHost-Pro Agent Runtime
License:        Proprietary
URL:            https://batchhost.local
Source0:        %{name}-%{version}.tar.gz

%description
BatchHost-Pro event-driven agent runtime (Execution Orchestration Engine).
This package installs the agent to run continuously in the background using systemd.

%prep
%setup -q

%build
# Use venv to install pyinstaller and build the single binary
python3 -m venv venv
source venv/bin/activate
pip install pyinstaller psutil
pyinstaller --onefile --name batchhost-agent agent_runtime.py
deactivate

%install
rm -rf %{buildroot}
mkdir -p %{buildroot}/root/batchhost-pro
mkdir -p %{buildroot}/etc/systemd/system

install -m 755 dist/batchhost-agent %{buildroot}/root/batchhost-pro/batchhost-agent
install -m 644 batchhost-agent.service %{buildroot}/etc/systemd/system/batchhost-agent.service

%clean
rm -rf %{buildroot}

%files
%defattr(-,root,root,-)
/root/batchhost-pro/batchhost-agent
/etc/systemd/system/batchhost-agent.service
%dir /root/batchhost-pro

%post
systemctl daemon-reload
systemctl enable batchhost-agent.service
systemctl restart batchhost-agent.service

%preun
if [ $1 -eq 0 ] ; then
    systemctl stop batchhost-agent.service
    systemctl disable batchhost-agent.service
fi

%postun
if [ $1 -eq 0 ] ; then
    systemctl daemon-reload
fi