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

import socket
from cm_api.api_client import ApiResource
import ConfigParser
import time
import httplib
import os
from fabric.api import *
from fabric.tasks import *
from fabric.context_managers import *

CMD_TIMEOUT = 360
HA_ENABLE_TIMEOUT = 600

config = ConfigParser.ConfigParser()
# Added to keep ConfingParser from lowercasing. 
config.optionxform = str

def config_grabber(section):
    temp = dict()
    for i in config.options(section):
        temp.update({i:config.get(section,i)})
    return temp

def get_cm_status(host):
    try:
        conn = httplib.HTTPConnection(host)
        conn.request('HEAD', '/')
        status = conn.getresponse().status
        return status
    except StandardError:
        return None
    finally:
        conn.close()


def deploy_to_gateways(service):
    
    """
    Deploys all client configurations to all GATEWAY roles.  
    @param service: This is the service object 
    """
  
    if service is not None:
        roles = service.get_roles_by_type("GATEWAY")
        if roles is not None: 
          for role in service.get_roles_by_type("GATEWAY"):
            print "Deploying Client Configs to host: " + role.name
            cmd = service.deploy_client_config(role.name)
            if not cmd.wait(CMD_TIMEOUT).success:
              print "Failed to deploy client configuration to GATEWAY: " + role.name
        else:
          raise Exception("This service does not support a GATEWAY role or GATEWAY not created.")
    else:
        raise Exception("The provided service is null") 


# Create HDFS and Format NN
def create_hdfs_service(config_dict, cluster):
    
    """
    This section creates the HDFS service, assigns roles, and updates the configurations based on
    the configuration file and starts the service.
    
    If you choose to enable HA, then this will automatically set up HDFS HA and enable the automatic
    failover.
    """
   
    print "Creating HDFS Services"
    hdfs = cluster.create_service("hdfs1", "HDFS")
    # Create NN/SNN -determine host for NN and SNN
            
    
    for host in config_grabber(cluster.name + '-en')['name.node'].split(','):
        print 'Creating Namenode: ' + host
        hdfs.create_role('hdfs1_NAMENODE_' + host.split('.')[0], 'NAMENODE', host)
    
    if config_dict.get('hdfs_ha') == False:
        host = config_grabber(cluster.name + '-en')['secondary.namenode']
        print 'Creating Secondary Namenode: ' + host
        hdfs.create_role('hdfs1_SECONDARYNAMENODE_' + host.split('.')[0], 'SECONDARYNAMENODE', host)
    
    for host in config_grabber(cluster.name + '-en')['full.list'].split(','):    
        print "Creating Gateway - Client Box: " + host
        hdfs.create_role('hdfs1_GATEWAY_' + host.split('.')[0], 'GATEWAY', host)
    
    #Config the cluster
    print 'Updating HDFS configuration'
    hdfs.update_config(svc_config=config_grabber('hdfs1-svc-config'))
    
    config_groups = config_grabber('HDFS')['config_groups']
    
    for config_group in config_groups.split(','):
        print 'Updating Config Role Group: ' + config_group
        temp_config_group = hdfs.get_role_config_group(config_group)
        temp_config_group.update_config(config_grabber(config_group))
    
    
    # Create Data Nodes on the dn's
    counter = 0
    for k,v in config_grabber(cluster.name + '-dn').iteritems():
        for host in v.split(','):      
            counter = counter + 1
            print 'Creating Datanode: ' + host
            hdfs.create_role('hdfs1_DATANODE_' + host.split('.')[0], 'DATANODE', host)
    
    if config_dict.get('hdfs_ha') == True:
        for host in config_grabber(cluster.name + '-en')['journal.node'].split(','):
            print 'Creating Journal Node: ' + host
            hdfs.create_role('hdfs1_JOURNALNODE_' + host.split('.')[0], 'JOURNALNODE', host)

        print 'Enabling NameNode HA with Quorum storage'

        if len(hdfs.get_roles_by_type('NAMENODE')) == 2:
            primary_nn = hdfs.get_roles_by_type('NAMENODE')[0]
            secondary_nn = hdfs.get_roles_by_type('NAMENODE')[1]
          
            print 'Enabling HDFS HA.'
            cmd = hdfs.enable_hdfs_ha(primary_nn.name, '/x/cdh/hdfs/nn/ha_edits',secondary_nn.name, '/x/cdh/hdfs/nn/ha_edits',config_grabber('hdfs1-NAMENODE-BASE')['dfs_federation_namenode_nameservice'], start_dependent_services=False, deploy_client_configs=True,enable_quorum_storage=True)
            if not cmd.wait(HA_ENABLE_TIMEOUT).success:
                print('Problems with Enabling HA NameNodes.  Continuing on just to try.')
            
            print 'Enabling automated failover of the HA NameNodes.'
            cmd = hdfs.enable_hdfs_auto_failover(config_grabber('hdfs1-NAMENODE-BASE')['dfs_federation_namenode_nameservice'],'hdfs1_FAILOVERCONTROLLER_' + primary_nn.hostRef.hostId.split('.')[0],'hdfs1_FAILOVERCONTROLLER_' + secondary_nn.hostRef.hostId.split('.')[0],cluster.get_service('zookeeper1'))
            if not cmd.wait(HA_ENABLE_TIMEOUT).success:
                raise Exception('Failed to enable HDFS Auto Failover.')
            print 'Done enabling HDFS Auto Failover.'
            print 'HDFS started.'

    else:
        print "deploying Client Configurations to Gateways"
        deploy_to_gateways(hdfs)  
 
        print "Formatting the NameNode"
        for nn in hdfs.get_roles_by_type('NAMENODE'):       
            cmd = hdfs.format_hdfs(nn.name)[0]
            if not cmd.wait(CMD_TIMEOUT).success:
              raise Exception("Failed to format HDFS")
            print "Done formatting the NameNode: " + str(nn.hostRef.hostId)

        print "Starting HDFS"
        cmd = hdfs.start()
        if not cmd.wait(CMD_TIMEOUT).success:
          raise Exception("Failed to start HDFS")
        print "HDFS Started"

def create_mapreduce_dirs():
    
    """
    This creates the base directories for running mapreduce jobs on the cluster.
    This will probably be deprecated in the near future if CM API picks it up.
    """
    
    sudo('hadoop fs -mkdir /user/' + env.user, user='hdfs')
    sudo('hadoop fs -chown ' + env.user + ' /user/' + env.user, user='hdfs')
    
    print 'Creating job history directory: ' + config_grabber("mapreduce1-JOBTRACKER-BASE")['mapred_job_tracker_history_completed_dir']
    sudo('hadoop fs -mkdir ' + config_grabber("mapreduce1-JOBTRACKER-BASE")['mapred_job_tracker_history_completed_dir'], user='hdfs')
    sudo('hadoop fs -chown mapred ' + config_grabber("mapreduce1-JOBTRACKER-BASE")['mapred_job_tracker_history_completed_dir'], user='hdfs')
    
    print 'Creating mapred system directory: ' + config_grabber("mapreduce1-svc-config")['mapred_system_dir'] 
    sudo('hadoop fs -mkdir ' + config_grabber("mapreduce1-svc-config")['mapred_system_dir'], user='hdfs')
    sudo('hadoop fs -chown mapred ' + config_grabber("mapreduce1-svc-config")['mapred_system_dir'], user='hdfs')
    
    print 'chmodding and chgrping on / to allow hadoop group write access'
    sudo('hadoop fs -chmod 775 /', user='hdfs')
    sudo('hadoop fs -chown hdfs:hadoop /', user='hdfs')
    
# Create MAPREDUCE and directories on HDFS
def create_mapred_service(config_dict, cluster, cm_server):
    
    """
    This section creates the Mapreduce service, assigns roles, and updates the configurations based on
    the configuration file and starts the service. 
    """
    
    print "Creating Mapreduce Services"
    mapred = cluster.create_service("mapreduce1", "MAPREDUCE")
    
    print "Updating Mapreduce configuration"
    mapred.update_config(svc_config=config_grabber("mapreduce1-svc-config"))
    config_groups = config_grabber("MAPREDUCE")['config_groups']
    for config_group in config_groups.split(','):
        print 'Updating Config Role Group: ' + config_group
        temp_config_group = mapred.get_role_config_group(config_group)
        temp_config_group.update_config(config_grabber(config_group))
    
    host = config_grabber(cluster.name + '-en')['job.tracker']
    print 'Creating Job Tracker: ' + host
    mapred.create_role('mapreduce1_JOBTRACKER_' + host.split('.')[0], 'JOBTRACKER', host)
    
    for host in config_grabber(cluster.name + '-en')['full.list'].split(','):    
        print "Creating Gateway - Client Box: " + host
        mapred.create_role('mapreduce1_GATEWAY_' + host.split('.')[0], 'GATEWAY', host)
        
    # Create Task Trackers and Gateways on the dn's
    counter = 0
    for k,v in config_grabber(cluster.name + '-dn').iteritems():
        for host in v.split(','):      
            counter = counter + 1
            print "Creating Task Trackers: " + host
            mapred.create_role('mapreduce1_TASKTRACKER_' + host.split('.')[0], 'TASKTRACKER', host)
            print "Creating Gateway - Client Box: " + host
            mapred.create_role('mapreduce1_GATEWAY_' + host.split('.')[0], 'GATEWAY', host)

    print "Creating user's HDFS home directory"
    with settings(host_string=cm_server):
        create_mapreduce_dirs()
 
    print "Starting Mapreduce"
    cmd = mapred.start()
    if not cmd.wait(CMD_TIMEOUT).success:
        print 'Problems Starting Mapreduce. Probably down Task Trackers.  Continuing.' 
    print "Mapreduce Started"

# Create Zookeeper Services
def create_zookeeper_service(config_dict, cluster):
    
    """
    This section creates the Zookeeper service, assigns roles, and updates the configurations
    based on the configuration file.  It also does an init and start
    """
    
    print "Creating Zookeeper Services"
    zk = cluster.create_service("zookeeper1", "ZOOKEEPER")

    print "Updating Zookeeper configuration"
    zk.update_config(svc_config=config_grabber("zookeeper1-svc-config"))
    config_groups = config_grabber("ZOOKEEPER")['config_groups']
    for config_group in config_groups.split(','):
        print 'Updating Config Role Group: ' + config_group
        temp_config_group = zk.get_role_config_group(config_group)
        temp_config_group.update_config(config_grabber(config_group))

    for host in config_grabber(cluster.name + '-en')['zookeepers'].split(','):
        print 'Creating Zookeeper: ' + host
        zk.create_role('zookeeper1_SERVER_' + host.split('.')[0], 'SERVER', host)
        cmd = zk.init_zookeeper(host.split('.')[0])
    
    # snooze for a bit to let the ZK's initialize     
    time.sleep(30) 

    print "Starting Zookeeper"
    cmd = zk.start()
    if not cmd.wait(CMD_TIMEOUT).success:
        print 'Failed to start Zookeeper.  Moving onto HBase configuration. You can start ZK and HBase manually'
    else:
        print "Zookeeper Started"

# Create HBase services
def create_hbase_service(config_dict, cluster): 

    """
    This section creates the HBase service, assigns roles, and updates the configurations based on
    the configuration file and starts the service. 
    """
        
    print "Creating HBase Services"
    hbase = cluster.create_service("hbase1", "HBASE")
    
    print "Updating HBase configurations"
    hbase.update_config(svc_config=config_grabber("hbase1-svc-config"))
    config_groups = config_grabber('HBASE')['config_groups']
    for config_group in config_groups.split(','):
        print 'Updating Config Role Group: ' + config_group
        temp_config_group = hbase.get_role_config_group(config_group)
        temp_config_group.update_config(config_grabber(config_group))
    
    # Create HMaster

    for host in config_grabber(cluster.name + '-en')['hbase.masters'].split(','):
        print "Creating HMaster: " + host
        hbase.create_role('hbase1_MASTER_' + host.split('.')[0], 'MASTER', host)
    
    for host in config_grabber(cluster.name + '-en')['full.list'].split(','):
        print 'Creating Gateway - Client Box: ' + host
        hbase.create_role('hbase1_GATEWAY_' + host.split('.')[0], 'GATEWAY', host)

  
    # Create Region Servers on the dn's
    counter = 0
    for k,v in config_grabber(cluster.name + '-dn').iteritems():
        for host in v.split(','):      
            counter = counter + 1
            print 'Creating region server: ' + host
            hbase.create_role('hbase1_REGIONSERVER_' + host.split('.')[0], 'REGIONSERVER', host)
        

    print"Creating HBase HDFS Base directory"
    cmd = hbase.create_hbase_root()
    if not cmd.wait(CMD_TIMEOUT).success:
        raise Exception("Failed to create root dir")
    print "Starting HBase"
    cmd = hbase.start()
    if not cmd.wait(CMD_TIMEOUT).success:
        print 'Problems Starting HBase. Probably down Region Servers.  Continuing.' 
    print "HBase Started"	

# Create Hive Services
def create_hive_service(config_dict, cluster):
    
    """
    This section creates the Hive metastore service, assigns roles, and updates the
    configurations based on the configuration file and starts the service.
    
    TODO: This is still not quite right. I think it still needs additional work.
    """
    
    print "Creating Hive Services"
    hive = cluster.create_service("hive1", "HIVE")

    print 'Updating Hive configuration'
    hive.update_config(svc_config=config_grabber('hive1-svc-config'))
    config_groups = config_grabber('HIVE')['config_groups']
    for config_group in config_groups.split(','):
        print 'Updating Config Role Group: ' + config_group
        temp_config_group = hive.get_role_config_group(config_group)
        temp_config_group.update_config(config_grabber(config_group))
 
    for host in config_grabber(cluster.name + '-en')['hive.metastores'].split(','):
        print "Creating Hive Metastore: " + host
        hive.create_role('hive1_HIVEMETASTORE_' + host.split('.')[0], 'HIVEMETASTORE', host)
    for host in config_grabber(cluster.name + '-en')['full.list'].split(','):    
        print 'Creating Gateway - Client Box: ' + host
        hive.create_role('hive1_GATEWAY_' + host.split('.')[0], 'GATEWAY', host)
        
    print 'Creating Hive Metastore Database'
    cmd = hive.create_hive_metastore_tables()
    if not cmd.wait(CMD_TIMEOUT).success:
         print 'Failed to create Hive Metastore Tables.  Moving onto the Hive HDFS directories'
    else:
         print 'Hive Metastore database created'

    print 'Creating Hive Warehouse Directories in HDFS'
    cmd = hive.create_hive_warehouse()
    if not cmd.wait(CMD_TIMEOUT).success:
         print 'Failed to create Hive Warehouse Directories in HDFS.'
    else:
         print 'Hive Warehouse directories Created in HDFS'

    print 'Starting Hive Metastore'
    cmd = hive.start()
    if not cmd.wait(CMD_TIMEOUT).success:
         print 'Failed to start the Hive Metastore. Moving on.  You can configure the Hive Metastore manually'
    else:
         print 'Hive Metastore Started'

def distribute_parcel(cluster, product, version):
    parcel = cluster.get_parcel(product,version)
    print 'Current parcel stage: ' + str(parcel.stage)
    if parcel.stage == 'UNAVAILABLE':
       print 'Giving CM time to find parcel information'
       while parcel.stage == 'UNAVAILABLE':
           print 'Sleeping 2 seconds.'
           print 'Parcel Status: ' + parcel.stage
           time.sleep(2)
           parcel = cluster.get_parcel(product,version)

    if parcel.stage == 'AVAILABLE_REMOTELY':
        print 'Beginning Parcel ' + product + ': ' + version + ' download.'
        parcel.start_download()
        while parcel.stage == 'DOWNLOADING' or parcel.stage == 'AVAILABLE_REMOTELY':
            parcel = cluster.get_parcel(product,version)
            time.sleep(10)
        print 'Parcel Status: ' + parcel.stage
    
    print 'Current parcel stage: ' + str(parcel.stage)
    if parcel.stage == 'DOWNLOADED':
        parcel.start_distribution()
        while parcel.stage == 'DOWNLOADED' or parcel.stage == 'DISTRIBUTING':
            parcel = cluster.get_parcel(product,version)
            time.sleep(10)
        print 'Parcel Status: ' + parcel.stage
    
    print 'Current parcel stage: ' + str(parcel.stage)
    if parcel.stage == 'DISTRIBUTED':
        cmd = parcel.activate()
        if not cmd.wait(CMD_TIMEOUT).success:
            print 'Error activating parcel.  Exiting now.'
        else:
            print 'Parcel ' + product + ' ' + version + ' successfully downloaded and activated.  Beginning cluster buildout.'
        
def create_cluster(config_dict):
    config.read(['./conf/hadrian.ini','./conf/cluster_specs.ini', './conf/cloudera-manager/cm.ini'])
    
    
    cm_cluster_name = config_grabber("Globals")['cm.cluster.name']
    cm_username = config_grabber("Globals")['cm.username']
    cm_password = config_grabber("Globals")['cm.password']
    cm_port = config_grabber("Globals")['cm.port']
    version = config_grabber('Globals')['cdh.cluster.version']
    cm_server = config_grabber(cm_cluster_name + '-en')['cm.server']
    
    #Grab all configuration files in the directory with the CM Cluster Name.
    
    for i in os.listdir('./conf/' + cm_cluster_name):
        config.read('./conf/' + cm_cluster_name + '/' + i)
    
    all_nodes = list()

    while (get_cm_status(cm_server + ':' + cm_port) != 200):
        print 'Waiting for CM Server to start... '
        time.sleep(15)
    
    api = ApiResource(cm_server, cm_port, cm_username, cm_password)
    # create cluster
    cluster = api.create_cluster(cm_cluster_name, version.upper())
    
    #Config CM
    print 'Applying any configuration changes to Cloudera Manager'
    cmanager = api.get_cloudera_manager()
    cmanager.update_config(config_grabber('cloudera-manager-updates'))
        
    planned_nodes = config_grabber(cm_cluster_name + '-en')['full.list'].split(',')
    for k, v in config_grabber(cm_cluster_name + '-dn').iteritems():
        for j in v.split(','):
            planned_nodes.append(j)
    
    # TODO make this smarter.  show which agents haven't checked in.  Add the option to continue without them.
    if len(api.get_all_hosts()) != len(planned_nodes):
        print 'Waiting for all agents to check into the CM Server before continuing.'
        
        while len(planned_nodes) > api.get_all_hosts():
            print 'Waiting for the final set of CM Agent nodes to check in.' 
            time.sleep(5)
        
    print 'Updating Rack configuration for data nodes.'
    all_hosts = list()
    for host in api.get_all_hosts():
        all_hosts.append(host.hostId)
        for k,v in config_grabber(cm_cluster_name + '-dn').iteritems():
            if host.hostname in v:
                print 'Setting host: ' + host.hostname + ' to rack /default/' + k
                host.set_rack_id('/default/' + k)
    
    print 'Adding all hosts to cluster.'
    cluster.add_hosts(all_hosts)

    # download CDH Parcels
    # TODO add some logic here to make the parcel list something that's read from the hadrian.ini
    # This will allow support for other CDH packages, Search, etc.
    if config_grabber('Globals')['cdh.distribution.method'] == 'parcels':
        distribute_parcel(cluster, 'CDH', config_grabber("Globals")['cdh.parcel.version'])
    
    if config_dict.get('hdfs_ha') == True:
        create_zookeeper_service(config_dict, cluster)
    create_hdfs_service(config_dict, cluster)    

    cmd = cluster.deploy_client_config()
    if not cmd.wait(CMD_TIMEOUT).success:
        print 'Failed to deploy client configurations'
    else:
        print 'Client configuration deployment complete.'

    create_mapred_service(config_dict, cluster, cm_server)
    if config_dict.get('hbase') == True:
        if config_dict.get('hdfs_ha') == False:
            create_zookeeper_service(config_dict, cluster)
        create_hbase_service(config_dict, cluster)
    if config_dict.get('hive') == True:
         create_hive_service(config_dict, cluster)
    print 'Starting final client configuration deployment for all services.'
    cmd = cluster.deploy_client_config()
    if not cmd.wait(CMD_TIMEOUT).success:
        print 'Failed to deploy client configuration.'
    else:
        print 'Client configuration deployment complete.  The cluster is all yours.  Happy Hadooping.'

