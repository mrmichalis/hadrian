/*
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
*/


CREATE ROLE scm LOGIN PASSWORD 'scm_password';
CREATE DATABASE scm OWNER scm encoding 'UTF8';
grant all privileges on database scm to scm;

CREATE ROLE amon_user LOGIN PASSWORD 'amon_password';
CREATE DATABASE activity_monitor OWNER amon_user encoding 'UTF8';
grant all privileges on database activity_monitor to amon_user;

CREATE ROLE smon_user LOGIN PASSWORD 'smon_password';
CREATE DATABASE service_monitor OWNER smon_user encoding 'UTF8';
grant all privileges on database service_monitor to smon_user;

CREATE ROLE rman_user LOGIN PASSWORD 'rman_password';
CREATE DATABASE reports_manager OWNER rman_user encoding 'UTF8';
grant all privileges on database reports_manager to rman_user;

CREATE ROLE hmon_user LOGIN PASSWORD 'hmon_password';
CREATE DATABASE host_monitor OWNER hmon_user encoding 'UTF8';
grant all privileges on database host_monitor to hmon_user;

CREATE ROLE metastore LOGIN PASSWORD 'metastore_password';
CREATE DATABASE metastore OWNER metastore encoding 'UTF8';
grant all privileges on database metastore to metastore;
commit;

commit;