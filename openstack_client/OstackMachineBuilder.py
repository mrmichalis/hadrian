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

from novaclient.v1_1 import client as nc
import ConfigParser
import time
import socket

    
config = ConfigParser.ConfigParser()
# Added to keep ConfingParser from lowercasing.
config.optionxform = str

def config_grabber(section):
    temp = dict()
    for i in config.options(section):
        temp.update({i:config.get(section,i)})
    return temp

def find_by_name(object_list, name):
    for i in object_list:
        if i.name == name:
            return i
    return None


def check_host_listening(host, port):

    """
    This is a method to check whether or not we can connect to the Ostack
    Host on port 22.  This is a final check before attempting to proceed
    with the remaining steps.
    """

    listening = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listening.connect((host, port))
        listening.shutdown(1)
        listening.close()
        return True
    except:
        return False  

def create_hosts(username, password, tenant_id, ssh_key, cluster_size):
    
    """
    TODO: This need some serious updating.  It works, or it did a while ago, but Hadrian has changed a lot on the config
    side.  We need to update this to work with latest/greatest Ostack and return a list of FQDNs instead of Nova Client
    names.
    
    The other problem is arbitrary hostname assignments by openstack and how to determine which service goes on which host.
    The existing host deployment is good, dealing with openstack's variety is tricky though.  Maybe we separate this step out?
    spin up VMs for me, then let the users do the configuration.  It would be a lot better if it was seamless.  decisions decisions.
    
    """
    config.read(['./conf/hadrian.ini','./conf/cluster_specs.ini'])

    nova = nc.Client(username, password, tenant_id, auth_url=config_grabber("OpenStack Information")['ostack.auth.url'])
    nova.authenticate()

    ostackImageName = find_by_name(nova.images.list(),config_grabber("OpenStack Information")['ostack.os.image.name'])
  
    hosts =  [] 
    for k,v in config_grabber(cluster_size).iteritems():
       hosts.append(nova.servers.create(k, ostackImageName, _find_by_name(nova.flavors.list(), v), key_name=ssh_key ))

    counter = len(hosts)
    hostnames = []
    while counter > 0:
      print "Polling Nova for build status" 
      time.sleep(10)
      for host in hosts:
         if nova.servers.get(host).status == 'ACTIVE':
           print host.name + ' status: ' + nova.servers.get(host).status
           fqdn = host.name + config_grabber("Host Information")['host.domain']
           if fqdn not in hostnames:
           	hostnames.append(host.name + config_grabber("Host Information")['host.domain'])
           	counter = counter - 1
         else:
           print host.name + " status: " + nova.servers.get(host).status 

    # make sure that all hosts are listening on 22 for ssh.  Apparently, ACTIVE in openstack doens't cover networking/sshd being online (awesome)
    temp_hosts = list(hostnames)
    while len(temp_hosts) > 0:
      print "Polling Hosts for ssh status"
      time.sleep(10)
      for host in hostnames:
         if check_host_listening(host, 22) is True:
            if host in temp_hosts:
                print host + ": networking online"
                temp_hosts.remove(host)
         else: 
            print host + ": networking still offline"

    return hostnames
