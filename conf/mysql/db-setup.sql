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

create database scm DEFAULT CHARACTER SET utf8;
grant all on scm.* to 'scm'@'%' IDENTIFIED BY 'scm_password';

create database amon DEFAULT CHARACTER SET utf8;
grant all on amon.* TO 'amon'@'%' IDENTIFIED BY 'amon_password';

create database smon DEFAULT CHARACTER SET utf8;
grant all on smon.* TO 'smon'@'%' IDENTIFIED BY 'smon_password';

create database rman DEFAULT CHARACTER SET utf8;
grant all on rman.* TO 'rman'@'%' IDENTIFIED BY 'rman_password';

create database hmon DEFAULT CHARACTER SET utf8;
grant all on hmon.* TO 'hmon'@'%' IDENTIFIED BY 'hmon_password';

create database metastore DEFAULT CHARACTER SET utf8;
grant all on metastore.* TO 'metastore'@'%' IDENTIFIED BY 'metastore_password';
commit;