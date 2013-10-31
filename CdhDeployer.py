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

import ConfigParser
import optparse
import getpass
import os
import time
from openstack_client import OstackMachineBuilder as osmb
from cm_client import CreateCdhCluster
from fabric.api import *
from fabric.tasks import *
from fabric.context_managers import *
from fabric.contrib.files import *
from utils import OsTuning as ost

config_dict = {}

config = ConfigParser.ConfigParser()
# Added to keep ConfingParser from lowercasing.
config.optionxform = str

def config_grabber(section):

    temp = dict()
    for i in config.options(section):
        temp.update({i:config.get(section,i)})
    return temp

# helper method to handle y/n input.
def yes_no_question(question, default=False):

    answer = raw_input(question)
    if answer == 'y':
        return True
    elif answer == 'n':
        return False
    else:
        while answer != 'y' and answer != 'n':
            answer = raw_input(question)
            if answer == 'y':
                return True
            elif answer == 'n':
                return False

# This method asks the user for information and then processes that input into the configuration dictionary
def process_user_input():

    config.read(['./conf/hadrian.ini','./conf/cluster_specs.ini'])
    cluster_name = config_grabber('Globals')['cm.cluster.name']
    for i in os.listdir('./conf/' + cluster_name):
        config.read('./conf/' + cluster_name + '/' + i)

    print "Please enter the following information so that we can build your Hadoop cluster for you."
    env.user = raw_input('Please enter your Linux account that has ssh/sudo to your hosts: ')
    env.password = getpass.getpass('Please enter your Linux passsword: ')
    
    if config_grabber('Globals')['system.database']  == 'mysql':
        db_root_password = getpass.getpass('Please enter your MySQL Root password: ')
        config_dict.update({'db_root_password': db_root_password })
    
    # The option to spin up Openstack VMs automatically, then deploy has been removed
    # for the time being.  There's some changes that need to be made to the OstackMachineBuilder
    # to support newest Openstack VM spin up.  There are a lot of other issues that need to be
    # figured out as well.  How to handle Ostack dynamic hostnames, variety in Openstack
    # networking configuration, etc.
    prebuilt_boxes = True   
    
    print 'Hadoop is a given, but please provide which other services you would like on your cluster.'
    cluster_version = config_grabber('Globals')['cdh.cluster.version']
    if cluster_version.startswith('cdh4'):
        hdfs_ha = yes_no_question('Would you like HDFS HA enabled [y/n]: ')
        mr_version = raw_input('Please select a MapReduce version (MRv1 or MRv2): ')
        while mr_version != 'MRv1' and mr_version != 'MRv2':
                mr_version = raw_input('Please select a MapReduce version (MRv1 or MRv2): ')
    else:
        hdfs_ha = False
        mr_version = 'MRv1'

    print 'Please answer yes or no for the various services to configure on your cluster.'
    hbase = yes_no_question('Do you want HBase/Zookeeper? (y/n): ')
    hive = yes_no_question('Do you want Hive? (y/n): ')

    # update config_dict with all the answers from the questions above.
    config_dict.update({'prebuilt_boxes': prebuilt_boxes})
    config_dict.update({'unixuser': env.user})
    config_dict.update({'mr_version': mr_version})
    config_dict.update({'hbase': hbase})
    config_dict.update({'hive': hive})
    config_dict.update({'hdfs_ha':hdfs_ha})
    
    # Create Fabric Role for the CM Server
    env.roledefs.update({'cm.server': [config_grabber(cluster_name + '-en')['cm.server']]})

def get_hosts():
    # Calls the process user input method above.
    process_user_input()

    # generate env.hosts list from the cluster_config.ini
    cluster_name = config_grabber('Globals')['cm.cluster.name']
    for host in config_grabber(cluster_name + '-en')['full.list'].split(','):
        env.hosts.append(host)
    
    for k, v in config_grabber(cluster_name + '-dn').iteritems():
        for host in v.split(','):
            env.hosts.append(host)
    
    

@parallel
def prep_cdh_cluster():

    """
    prep_cdh_cluster is the primary workhorse of Hadrian.  This is run on ALL nodes.
    First, it executes a OS tune from workouts/OsTuning.  full_tune() is just a wrapper around all of the methods.
    Second, it deploys the yum repo files to each host using a remote wget command.
    Third, it installs CDH RPMs (if the users is not using parcels)
    Fourth, it installs the Cloudera Manager agent and starts it.
    """
    
    # run a full tune on each host.  This takes care of any nastiness that we might run into with config settings.
    print 'Executing a full tune on host.'
    ost.full_tune()
    version = config_grabber('Globals')['cdh.cluster.version']
    with hide('output'):
        # check for repository file
        cm_repo_file = config_grabber('Yum Repo Information')['cm.yum.repo.file'].rsplit('/',1)
        if len(cm_repo_file) == 2:
            if exists('/etc/yum.repos.d/' + cm_repo_file[1]) == False:
                with cd('/etc/yum.repos.d'):
                    sudo('wget ' + config_grabber('Yum Repo Information')['cm.yum.repo.file'])
        else:
            sys.exit('ERROR: Your CM Repository URL is incorrectly formatted in your hadrian.ini. ' +
                     'Example: cm.yum.repo.file=http://archive.cloudera.com/cm4/redhat/6/x86_64/cm/cloudera-manager.repo')

        #Snag the CDH Repository File
        if config_grabber('Globals')['cdh.distribution.method'] == 'rpms':
            cdh_repo_file = config_grabber('Yum Repo Information')['cdh.yum.repo.file'].rsplit('/',1)
            if len(cdh_repo_file) == 2:
                if exists('/etc/yum.repos.d/' + cdh_repo_file[1]) == False:
                    with cd('/etc/yum.repos.d'):
                        sudo('wget ' + config_grabber('Yum Repo Information')['cdh.yum.repo.file'])
            else:
                sys.exit('ERROR: Your CDH Repository URL is incorrectly formatted in your hadrian.ini. ' + 
                         'Example: cdh.yum.repo.file=http://archive.cloudera.com/cdh4/redhat/6/x86_64/cdh/cloudera-cdh4.repo')
        
        # Setting set -o vi.  I can't stand it when that isn't set. -mikeg
        if exists('/root/.bashrc') == True:
            if contains('/root/.bashrc', 'set -o vi') == False:
                print 'Appeding set -o vi to /root/.bashrc. Embrace the power of vi.'
                append('/root/.bashrc', 'set -o vi', use_sudo=True)

        if exists(config_grabber('JVM Information')['jdk.home.dir']) == False:
            print 'JDK home dir does not exist, downloading JDK RPM'
            with cd('/tmp'):
                sudo('wget ' + config_grabber('JVM Information')['jdk.download.url'])
                sudo('chmod 744 *.rpm')
                sudo('rpm -Uvh *.rpm')
    
        # If cdh.distribution.method is rpms, then this section comes into play.  This is a bit forward thinking.  Most of these won't
        # be installed because Hadrian doesn't support them yet.
        if config_grabber('Globals')['cdh.distribution.method'] == 'rpms':
            print 'Installing Hadoop RPMS.'
            if version.startswith('cdh4'):
                
                print 'Installing HDFS Base'
                sudo('yum install hadoop-hdfs hadoop-client hadoop-httpfs -y')
    
                if config_dict.get('mr_version')  == 'MRv2':
                    sudo('yum install hadoop-mapreduce -y')
                else:
                    sudo('yum install hadoop-0.20-mapreduce -y')
                if config_dict.get('hbase') == True:
                    sudo('yum install hbase zookeeper -y')
                if config_dict.get('hdfs_ha') == True:
                    sudo('yum install zookeeper -y')
                if config_dict.get('mahout')  == True:
                    sudo('yum install mahout -y')
                if config_dict.get('pig')  == True:
                    sudo('yum install pig -y')
                if config_dict.get('hive')  == True:
                    sudo('yum install hive -y')
                if config_dict.get('hcatalog')  == True:
                    sudo('yum install hcatalog -y')
    
            elif version.startswith('cdh3'):
                sudo('yum install hadoop-0.20 hadoop-0.20-native hue-plugins -y')
                if config_dict.get('hbase') == True:
                    sudo('yum install hadoop-hbase hadoop-zookeeper -y')
                if config_dict.get('mahout')  == True:
                    sudo('yum install mahout -y')
                if config_dict.get('pig')  == True:
                    sudo('yum install hadoop-pig -y')
                if config_dict.get('hive')  == True:
                    sudo('yum install hadoop-hive -y')
    
            else:
                print 'Unknown CDH version'
                
        # continue with agent install steps.  even cm server should have an agent after all.
        sudo('yum install cloudera-manager-agent cloudera-manager-daemons -y')
        cluster_name = config_grabber('Globals')['cm.cluster.name']    
        sed('/etc/cloudera-scm-agent/config.ini', 'server_host=localhost', 'server_host=' + config_grabber(cluster_name + '-en')['cm.server'], use_sudo=True)
        sudo('service cloudera-scm-agent start')

@roles('cm.server')
def install_cm_server():
    """
    This method does exactly what it's named.  It installs the Cloudera Manager Server and starts it.
    It also installs postgresql server if system.database is postgresql.
    If system.database=mysql is in the hadrian.ini, then it simply creates the users based on input from the process_user_input() and hadrian.ini.
    TODO: embedded db support should also be an option.
    """
    cluster_name = config_grabber('Globals')['cm.cluster.name']
    with hide('output'):
        if config_grabber(cluster_name + '-en')['cm.server'] == env.host:
            sudo('yum install cloudera-manager-server cloudera-manager-daemons -y')
            with settings(warn_only=True):
                 sudo('useradd cloudera-scm')
            db_type = config_grabber('Globals')['system.database']

            if db_type == 'embedded':
                sudo('yum install cloudera-manager-server-db -y')
                sudo('service cloudera-scm-server-db start')
            else:                
                db_port = config_grabber(db_type)['db.port']
                db_root_password = config_dict.get('db_root_password')
                
                if db_type == 'postgresql':
                    db_host = env.host               
                else:
                    db_host = config_grabber(db_type)['db.host']
    
    
                if config_grabber('Globals')['system.database'] == 'postgresql':
                    config.read('./conf/postgresql/postgresql.ini')
                    sudo('yum install postgresql-server postgresql-jdbc -y')
    
                    # TODO allow Postgres to be configured to use a different directory for it's data dir.
                    postgresql_datadir = '/var/lib/pgsql/data'
    
                    print 'Init PostgreSQL Server'
                    sudo('/etc/init.d/postgresql initdb')
    
                    put('./conf/postgresql/pg_hba.conf', postgresql_datadir, use_sudo=True)
                    sudo('chown postgres:postgres ' + postgresql_datadir + '/pg_hba.conf')
                    put('./conf/postgresql/postgresql.conf', postgresql_datadir, use_sudo=True)
                    sudo('chown postgres:postgres ' + postgresql_datadir + '/postgresql.conf')
                    print 'Starting the PostgreSQL Server'
                    sudo('/etc/init.d/postgresql start')
    
                # Initialize the CM database
                put('./conf/' + db_type + '/db-setup.sql', '/tmp/.')
    
                print 'Executing Database updates and obscuring passwords for security.'
                with hide('running'):
                    sed('/tmp/db-setup.sql', 'scm_password', config_grabber('DB Users')['cm.db.password'])
                    sed('/tmp/db-setup.sql', 'amon_password', config_grabber('DB Users')['amon.db.password'])
                    sed('/tmp/db-setup.sql', 'smon_password', config_grabber('DB Users')['smon.db.password'])
                    sed('/tmp/db-setup.sql', 'rman_password', config_grabber('DB Users')['rman.db.password'])
                    sed('/tmp/db-setup.sql', 'hmon_password', config_grabber('DB Users')['hmon.db.password'])
                    sed('/tmp/db-setup.sql', 'metastore_password', config_grabber('DB Users')['metastore.db.password'])

                # Create the datbase users/roles/schemas/whatever.
                if db_type == 'mysql':
                    with hide('running'):
                        sudo('mysql -u root -h ' + db_host + ' -P ' + db_port + ' -p' + db_root_password + ' < /tmp/db-setup.sql')
                elif db_type == 'postgresql':
                    sudo('psql < /tmp/db-setup.sql', user='postgres')
    
                #Usage: scm_prepare_database.sh [options] database-type database-name username password
                with cd('/usr/share/cmf/schema'):
                    print 'Preparing Cloudera Manager Database.  Obscuring output for security.'
                    with hide('running'):
                        if db_type == 'postgresql':
                            sudo('./scm_prepare_database.sh ' + db_type + ' scm scm ' + config_grabber('DB Users')['cm.db.password'])
                        else:
                            sudo('./scm_prepare_database.sh -P ' + db_port + ' -p' + db_root_password + ' -h ' + db_host + ' ' + db_type + ' scm scm ' + config_grabber('DB Users')['cm.db.password'])

            #Get rid of files with passwords in them.  Can't leave those laying around in /tmp
            if exists('/tmp/db-setup.sql'):
                sudo('rm /tmp/db-setup.sql')
            if exists('/tmp/db-setup.sql.bak'):
                sudo('rm /tmp/db-setup.sql.bak')
            
        print 'Starting Cloudera Manager Server'
        sudo('service cloudera-scm-server start')
        
        #Start configuring CM and the cluster!  Go man go!
        CreateCdhCluster.create_cluster(config_dict)
            
        


################################################################################################################################
#
#			This is to clean up CDH.  It's the nuclear option so use with care.
#
################################################################################################################################
@parallel
def clean_cdh():
  with settings(warn_only=True):
    #Grab the CDH version out of the config file.  This will drive the rest of config file reads.
    cluster_name = config_grabber('Globals')['cm.cluster.name']
    version = config_grabber('Globals')['cdh.cluster.version']
    with hide('output'):
        if config_grabber(cluster_name + '-en')['cm.server'] == env.host:
            sudo('service cloudera-scm-server stop')
            sudo('yum erase cloudera-manager-server -y')
            if exists('/var/run/cloudera-scm-server') == True:
                sudo('rm -rf /var/run/cloudera-scm-server/*')
            if exists('/var/log/cloudera-scm-server') == True:
                sudo('rm -rf /var/log/cloudera-scm-server/*')


            if config_grabber('Globals')['system.database'] == 'postgresql':
                print 'Removing postgres'
                sudo('yum erase postgresql-server postgresql-jdbc -y')
                sudo('rm -rf /var/lib/pgsql')

        sudo('service cloudera-scm-agent stop')
        sudo('sudo yum erase cloudera-manager-agent cloudera-manager-daemons -y')

        if exists('/var/run/cloudera-scm-agent') == True:
            sudo('rm -rf /var/run/cloudera-scm-agent')

        if exists('/var/log/cloudera-scm-agent') == True:
            sudo('rm -rf /var/log/cloudera-scm-agent')

        print 'Removing Hadoop binaries'
        if version.startswith('cdh4'):
            print 'Removing CDH4'
            sudo('yum erase hadoop-hdfs hadoop-client hadoop-httpfs hadoop-mapreduce hbase zookeeper pig hive hcatalog -y')

        elif version.startswith('cdh3'):
            sudo('yum erase hadoop-0.20 hadoop-0.20-native hue-plugins hadoop-hbase hadoop-zookeeper mahout hadoop-pig hadoop-hive -y')

        else:
            print 'Unknown CDH version'

        print 'Deleting Hadoop System and Log directories'
        if config_grabber('hdfs1-NAMENODE-BASE')['dfs_name_dir_list'] is not None:
            for dir in config_grabber('hdfs1-NAMENODE-BASE')['dfs_name_dir_list'].split(','):
                if exists(dir) == True:
                    sudo('rm -rf ' + dir)

        if config_grabber('hdfs1-NAMENODE-BASE')['namenode_log_dir'] is not None:
            dir = config_grabber('hdfs1-NAMENODE-BASE')['namenode_log_dir']
            if exists(dir) == True:
                sudo('rm -rf ' + dir)

        if config_grabber('hdfs1-SECONDARYNAMENODE-BASE')['fs_checkpoint_dir_list'] is not None:
            for dir in config_grabber('hdfs1-SECONDARYNAMENODE-BASE')['fs_checkpoint_dir_list'].split(','):
                if exists(dir) == True:
                    sudo('rm -rf ' + dir)

        if config_grabber('hdfs1-SECONDARYNAMENODE-BASE')['secondarynamenode_log_dir'] is not None:
            dir = config_grabber('hdfs1-SECONDARYNAMENODE-BASE')['secondarynamenode_log_dir']
            if exists(dir) == True:
                sudo('rm -rf ' + dir)

        if config_grabber('hdfs1-DATANODE-BASE')['dfs_data_dir_list'] is not None:
            for dir in config_grabber('hdfs1-DATANODE-BASE')['dfs_data_dir_list'].split(','):
                if exists(dir) == True:
                    sudo('rm -rf ' + dir)

        if config_grabber('hdfs1-DATANODE-BASE')['datanode_log_dir'] is not None:
            dir = config_grabber('hdfs1-DATANODE-BASE')['datanode_log_dir']
            if exists(dir) == True:
                sudo('rm -rf ' + dir)
                
        if version.startswith('cdh4'):
            if config_grabber('hdfs1-JOURNALNODE-BASE').has_key('dfs_journalnode_edits_dir'):
                if config_grabber('hdfs1-JOURNALNODE-BASE')['dfs_journalnode_edits_dir'] is not None:
                    dir = config_grabber('hdfs1-JOURNALNODE-BASE')['dfs_journalnode_edits_dir']
                    if exists(dir) == True:
                        sudo('rm -rf ' + dir)    

        if config_dict.get('mr_version')  == 'MRv2':
            print 'Deleting Yarn Directories'

            if config_grabber('yarn1-RESOURCEMANAGER-BASE')['resource_manager_log_dir'] is not None:
                dir = config_grabber('yarn1-RESOURCEMANAGER-BASE')['resource_manager_log_dir']
                if exists(dir) == True:
                    sudo('rm -rf ' + dir)

            if config_grabber('yarn1-JOBHISTORY-BASE')['mr2_jobhistory_log_dir'] is not None:
                dir = config_grabber('yarn1-JOBHISTORY-BASE')['mr2_jobhistory_log_dir']
                if exists(dir) == True:
                    sudo('rm -rf ' + dir)

            if config_grabber('yarn1-NODEMANAGER-BASE')['yarn_nodemanager_local_dirs'] is not None:
                for dir in config_grabber('yarn1-NODEMANAGER-BASE')['yarn_nodemanager_local_dirs'].split(','):
                    if exists(dir) == True:
                       sudo('rm -rf ' + dir)

            if config_grabber('yarn1-NODEMANAGER-BASE')['yarn_nodemanager_log_dirs'] is not None:
                for dir in config_grabber('yarn1-NODEMANAGER-BASE')['yarn_nodemanager_log_dirs'].split(','):
                    if exists(dir) == True:
                       sudo('rm -rf ' + dir)

            if config_grabber('yarn1-NODEMANAGER-BASE')['node_manager_log_dir'] is not None:
                dir = config_grabber('yarn1-NODEMANAGER-BASE')['node_manager_log_dir']
                if exists(dir) == True:
                    sudo('rm -rf ' + dir)
        else:
            print 'Deleting Mapreduce directories'
            if config_grabber('mapreduce1-JOBTRACKER-BASE')['jobtracker_mapred_local_dir_list'] is not None:
                for dir in config_grabber('mapreduce1-JOBTRACKER-BASE')['jobtracker_mapred_local_dir_list'].split(','):
                    if exists(dir) == True:
                       sudo('rm -rf ' + dir)

            if config_grabber('mapreduce1-JOBTRACKER-BASE')['jobtracker_log_dir'] is not None:
                dir = config_grabber('mapreduce1-JOBTRACKER-BASE')['jobtracker_log_dir']
                if exists(dir) == True:
                    sudo('rm -rf ' + dir)

            if config_grabber('mapreduce1-TASKTRACKER-BASE')['tasktracker_mapred_local_dir_list'] is not None:
                for dir in config_grabber('mapreduce1-TASKTRACKER-BASE')['tasktracker_mapred_local_dir_list'].split(','):
                    if exists(dir) == True:
                       sudo('rm -rf ' + dir)

            if config_grabber('mapreduce1-TASKTRACKER-BASE')['tasktracker_log_dir'] is not None:
                dir = config_grabber('mapreduce1-TASKTRACKER-BASE')['tasktracker_log_dir']
                if exists(dir) == True:
                    sudo('rm -rf ' + dir)

        print 'Deleting HBase Directories'

        if config_grabber('hbase1-MASTER-BASE')['hbase_master_log_dir'] is not None:
            dir = config_grabber('hbase1-MASTER-BASE')['hbase_master_log_dir']
            if exists(dir) == True:
                sudo('rm -rf ' + dir)

        if config_grabber('hbase1-REGIONSERVER-BASE')['hbase_regionserver_log_dir'] is not None:
            dir = config_grabber('hbase1-REGIONSERVER-BASE')['hbase_regionserver_log_dir']
            if exists(dir) == True:
                sudo('rm -rf ' + dir)

        print 'Deleting Zookeeper Directories'
        if config_grabber('zookeeper1-SERVER-BASE').has_key('zk_server_log_dir'):
            if config_grabber('zookeeper1-SERVER-BASE')['zk_server_log_dir'] is not None:
                dir = config_grabber('zookeeper1-SERVER-BASE')['zk_server_log_dir']
                if exists(dir) == True:
                    sudo('rm -rf ' + dir)

        if config_grabber('zookeeper1-SERVER-BASE').has_key('dataDir'):
            if config_grabber('zookeeper1-SERVER-BASE')['dataDir'] is not None:
                dir = config_grabber('zookeeper1-SERVER-BASE')['dataDir']
                if exists(dir) == True:
                    sudo('rm -rf ' + dir)
    
        if exists('/var/lib/zookeeper'):
            sudo('rm -rf /var/lib/zookeeper')

        print 'Deleting Hive Directories'

        if config_grabber('hive1-HIVEMETASTORE-BASE').has_key('hive_log_dir'):
            if config_grabber('hive1-HIVEMETASTORE-BASE')['hive_log_dir'] is not None:
                dir = config_grabber('hive1-HIVEMETASTORE-BASE')['hive_log_dir']
                if exists(dir) == True:
                    sudo('rm -rf ' + dir)
        
        if exists('/opt/cloudera/parcels') == True:
            sudo('rm -rf /opt/cloudera/parcels')
            
        if exists('/usr/lib/hadoop'):
            sudo('rm -rf /usr/lib/hadoop')
        
        if exists('/usr/lib/hadoop-0.20'):
            sudo('rm -rf /usr/lib/hadoop-0.20')
    
        # check for repository file
        cm_repo_file = config_grabber('Yum Repo Information')['cm.yum.repo.file'].rsplit('/',1)
        if len(cm_repo_file) == 2:
            if exists('/etc/yum.repos.d/' + cm_repo_file[1]) == True:
                sudo('rm -f /etc/yum.repos.d/' + cm_repo_file[1])
                sudo('yum clean metadata')
        else:
            sys.exit('ERROR: Your CM Repository URL is incorrectly formatted in your hadrian.ini. ' +
                     'Example: cm.yum.repo.file=http://archive.cloudera.com/cm4/redhat/6/x86_64/cm/cloudera-manager.repo')


        cdh_repo_file = config_grabber('Yum Repo Information')['cdh.yum.repo.file'].rsplit('/',1)
        if len(cdh_repo_file) == 2:
            if exists('/etc/yum.repos.d/' + cdh_repo_file[1]) == True:
                sudo('rm -f /etc/yum.repos.d/' + cdh_repo_file[1])
                sudo('yum clean metadata')
        else:
            sys.exit('ERROR: Your CDH Repository URL is incorrectly formatted in your hadrian.ini.  Example: cdh.yum.repo.file=http://archive.cloudera.com/cdh4/redhat/6/x86_64/cdh/cloudera-cdh4.repo')
    

