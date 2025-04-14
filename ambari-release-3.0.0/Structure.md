# Structure

## Directory

### Ambari Server

* /usr/lib/ambari-server/web
  * *.jar (ambari-admin, ambari-metrics-common ambari-server ambari-server-spi ambari-serviceadvisor ambari-views ...)
  * web   (ambari-web)
  * lib   (Python)
    * ambari_commons
    * ambari_jinja2
    * ambari_pbkdf2
    * ambari_pyaes
    * ambari_server
    * ambari_simplejson
    * resource_management 
* /var/lib/ambari-server
  * ambari-env.sh
  * ambari-sudo.sh
  * create-python-wrap.sh
  * install-helper.sh
  * data
  * keys
  * resources
    * *.sql
    * common-services
    * stacks
    * upgrade
    * views
    * mpacks-v2
    * stack-hooks
    * ...
* /var/log/ambari-server
* /etc/ambari-server/conf
  * ambari.properties
  * krb5JAASLogin.conf
  * log4j.properties
  * metrics.properties
* /etc/init.d
  * ambari-server 

### Ambari Server

* /var/log/ambari-agent
* /etc/ambari-agent/conf
    * ambari-agent.ini
    * logging.conf.sample
* /etc/init.d
    * ambari-agent 

