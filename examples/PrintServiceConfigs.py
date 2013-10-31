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

from cm_api.api_client import ApiResource

def main():

   """
   This is an example script for printing the default configurations for a CM Service.
   It's rough, but it gets the job done.  This  is how you can see all of the settings
   you've made for service along iwth the defaults.  Helpful if you are just curious
   what things look like.  For a more Hadrian-ish way to export configurations,
   see ExportConfigs.py
   """

   api = ApiResource('<cloudera manager server>', 7180, '<username>', '<password>')
   cluster = api.get_cluster('CM')
   service = cluster.get_service('<service name>')
   
   for i in service.get_all_role_config_groups():
      print '--------------------------------------------------------'
      print i.name
      print '--------------------------------------------------------'
      for k,v in i.get_config('full').iteritems():
          if v.value is None:  
             print k + ' - default - ' + str(v.default)
          else: 
             print k + ' - ' + str(v.value)

if __name__ == '__main__':
        main()