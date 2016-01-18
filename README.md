WWmode
======

**WWmode is a tool for collecting data about devices in network, store it in
database and search through it.**

As of now it support db update and some search operations.

### Update

To update a db simply run it with *-u/--update* key. It take some time, log any
intresting events and even check hosts for some errors.

### Search

To search through db records use *-f/--full-search value* key. 
For example: `-f info` to find devices with 'info' string in any of that
field:
    
    * IPv4 address - ip
    * Domain name - dname 
    * Contact - contact
    * Locatoin - location
    * Device model - model
    * Firmware version - firmware

You can search for VLANs straight with *-v/--find-vlan tag* option.

### Show

To show all records in short use *-s/--show-all* key. To show full output on one
record use *-d/--show value* where value can be an IPv4 address or FQDN.
