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


import sys
import os
from cm_api.api_client import ApiResource
from cm_api.api_client import ApiException
import argparse
import getpass
import urllib2

def main():

    """
    This is a script to export a current Cloudera Manager cluster configuration into an Hadrian supported format.
    You can then use these configuration files as the basis for your new cluster configs.
    """
    
    parser = argparse.ArgumentParser(description='Export Cloudera Manager configs in an Hadrian friendly format.')
    parser.add_argument('-H', '--host', '--hostname', action='store', dest='hostname', required=True, help='CM Server Name')
    parser.add_argument('-p', '--port', action='store', dest='port', type=int, default=7180, help='CM Port')
    parser.add_argument('-u', '--user', '--username', action='store', dest='username', required=True, help='CM username')
    args = parser.parse_args()
    
    password = getpass.getpass('Please enter your Cloudera Manager passsword: ')
    api = ApiResource(args.hostname, args.port, args.username, password, version=4)

    for cluster in api.get_all_clusters():
        conf_dir = './confs/' + cluster.name
        if not os.path.exists(conf_dir):
            os.makedirs(conf_dir)
        for service in cluster.get_all_services():
            with open(conf_dir + '/' + service.name + '.ini', 'w') as f:
               print 'Dumping Service config for ' + service.name
               rcg = list()
               for i in service.get_all_role_config_groups():
                  rcg.append(i.name)
               
               f.write('[' + service.type + ']\n')
               f.write('config_groups=' + ','.join(rcg))
               f.write('\n\n')
               f.write('[' + service.name + '-svc-config]\n')
               for item in service.get_config():
                  for k,v in item.iteritems():
                      f.write(k + '=' + str(v) + '\n')
            
               for i in service.get_all_role_config_groups():
                  f.write('\n')
                  f.write('[' + i.name + ']\n')
                  for k,v in i.get_config('full').iteritems():
                      if v.value is not None:
                          f.write(k + '=' + str(v.value) + '\n')
               f.close()
                     
      else:
         print 'Cluster config dir already exists.  Please rename or remove existing config dir: ' + conf_dir
           
   
if __name__ == '__main__':
        main()
