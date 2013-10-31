#!/usr/bin/env python

"""
Copyright 2013 eBay Software Foundation

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from fabric.api import *
from fabric.tasks import *
from fabric.context_managers import *
from fabric.contrib.files import *

# TODO: We need to figure out a good way to turn off atime and nodiratime on
# the data mounts.  Tricky, I think, but not impossible. maybe by using
# the user's dfs.name.dir and dfs.data.dir settings?  that would probably work.

@parallel
def disable_selinux():
    #  Check and Disable SELinux
    print 'Checking for SELinux and disabling it if not already disabled.'
    if exists('/etc/selinux/config'):
        if contains('/etc/selinux/config','SELINUX=enforcing'):
            sed('/etc/selinux/config','SELINUX=enforcing','SELINUX=disabled',use_sudo=True)
            sudo('/usr/sbin/setenforce 0')
        elif contains('/etc/selinux/config','SELINUX=permissive'):
            sed('/etc/selinux/config','SELINUX=permissive','SELINUX=disabled',use_sudo=True)
            sudo('/usr/sbin/setenforce 0')
        # just making sure it's permissive.
        sudo('/usr/sbin/setenforce 0')

@parallel
def disable_iptables():    
    #  Check for iptables and disable it
    print 'Disabling iptables and ip6tables and chkconfig-ing them off'
    if exists('/etc/init.d/iptables'):
        sudo('/etc/init.d/iptables stop')
        sudo('chkconfig iptables off')
    if exists('/etc/init.d/ip6tables'):
        sudo('/etc/init.d/ip6tables stop')
        sudo('chkconfig ip6tables off')

@parallel        
def fix_swappiness():
    if contains('/etc/sysctl.conf', 'vm.swappiness=0') == False:
        comment('/etc/sysctl.conf', 'vm.swappiness=*', use_sudo=True)
        append('/etc/sysctl.conf', 'vm.swappiness=0', use_sudo=True)

@parallel
def set_overcommit_mem():
    if contains('/etc/sysctl.conf', 'vm.overcommit_memory=1', exact=True) == False:
         sudo('echo 1 > /proc/sys/vm/overcommit_memory')
         if contains('/etc/sysctl.conf', 'vm.overcommit_memory='):
              comment('/etc/sysctl.conf', 'vm.overcommit_memory=', use_sudo=True)
         append('/etc/sysctl.conf', 'vm.overcommit_memory=1', use_sudo=True)

@parallel         
def turn_off_trans_huge_pages():
    os_name = run('uname -a')
    if '.el6.' in os_name:
        if exists('/sys/kernel/mm/redhat_transparent_hugepage/defrag'):
            sudo('echo never > /sys/kernel/mm/redhat_transparent_hugepage/defrag')
         
@parallel         
def full_tune():
    disable_selinux()
    disable_iptables()
    fix_swappiness()
    set_overcommit_mem()
    turn_off_trans_huge_pages()