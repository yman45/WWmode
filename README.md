WWmode
======

**WWmode is a tool for collecting data about devices in network, store it in
database and search through it.**

It automaticly generate configuration for newly found hosts and email it.
Hosts which domain names was change considered new.

### Update

To update a db simply run it with *-U/--update* key. It take some time and log 
some intresting events.

### Search

*-S Group*
To search through db records use *-f/--full-search VALUE* key. 
For example: `-S -f info` to find devices with 'info' string in any of that
field:
    
    * IPv4 address - ip
    * Domain name - dname 
    * Contact - contact
    * Location - location
    * Device model - model
    * Firmware version - firmware

You can search for VLAN chains straight with *-l/--find-vlan TAG* option.
To show device chain from some device to top *-c/--chain DEVICE* option,
where DEVICE are FQDN or IPv4.
To find switches with firmware older than given use 
*-o/--older-software MODEL VERSION*.
To find switches with firmware version older than newest one in DB use
*-t/--outdated* option.
To find switches of some model use *-m/--model MODEL* option.
To show all records in short use *-a/--show-all* key. To show full output on one
record use *-d/--device DEVICE* where value can be an IPv4 address or FQDN. To show
switches considered inactive (not contacted last time) use *-i/--inactive* key.


### Generate

*-G group*
Generate usefull info from DB records. 
To generate plain list of hosts use *-P/--plain* key.
For Nagios list use *-N/--nagios*.
For DNS records - *-D/--dns*.
For Trac table - *-T/--trac*.
For RANCID db - *-R/--rancid*.

### Verbose output
For verbose output to console use *-v/--verbose* up to 2 times.
