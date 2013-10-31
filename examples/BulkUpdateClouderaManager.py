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

import argparse
import os
from cm_api.api_client import ApiResource
from cm_api.api_client import ApiException
import ConfigParser
import getpass

# Defining a global parameter for client deployment timeouts
CMD_TIMEOUT = 120

config = ConfigParser.ConfigParser()
# Added to keep ConfingParser from lowercasing. 
config.optionxform = str


def config_grabber(section):
    temp = dict()
    for i in config.options(section):
        temp.update({i:config.get(section,i)})
    return temp

def main():
    
    """
    TODO: This probably needs some work.  You get the idea though.  
    An example of how to do a bulk config update to Cloudera Manager.  This is helpful if you have a bunch of changes
    That you want to make but don't want to use the GUI.  
    """
    
    parser = argparse.ArgumentParser(description='Cloudera Manager Bulk Config Update Script')
    parser.add_argument('-H', '--host', '--hostname', action='store', dest='hostname', required=True, help='CM server host')
    parser.add_argument('-p', '--port', action='store', dest='port', type=int, default=7180, help='example: 7180')
    parser.add_argument('-u', '--user', '--username', action='store', dest='username', required=True, help='example: admin')
    parser.add_argument('-c', '--cluster', action='store', dest='cluster', required=True, help='example: hadrian-cluster')
    args = parser.parse_args() 
    password = getpass.getpass('Please enter your Cloudera Manager passsword: ')
    
    # read configuration files:
    for i in os.listdir('./conf/' + args.cluster):
        config.read('./conf/' + args.cluster + '/' + i)
    
    api = ApiResource(args.hostname, args.port, args.username, password)
    cluster = api.get_cluster(args.cluster)
    services = cluster.get_all_services()
   
    # update services based with configuration file parameters   
    for service in services:
        if config_grabber.has_section(service.type):
            service.update_config(svc_config=config_grabber(service.name + '-svc-config'))
            config_groups = config_grabber(service.name)['config_groups']
            for config_group in config_groups.split(','):
                print section
                temp_config_group = service.get_role_config_group(section)
                temp_config_group.update_config(config_grabber(section))
        else:
            print 'unknown service: ' + service.name

    print 'Starting final client configuration deployment for all services.'
    cmd = cluster.deploy_client_config()
    if not cmd.wait(CMD_TIMEOUT).success:
        print 'Failed to deploy client configuration.'

if __name__ == '__main__':
        main()

