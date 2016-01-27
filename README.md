WWmode
======

**WWmode is a tool for collecting data about devices in network, store it in
database and search through it.**

As of now it support db update and some search operations.

### Update

To update a db simply run it with *-U/--update* key. It take some time, log any
intresting events and even check hosts for some errors.

### Search

*-F Group*
To search through db records use *-f/--full-search VALUE* key. 
For example: `-F -f info` to find devices with 'info' string in any of that
field:
    
    * IPv4 address - ip
    * Domain name - dname 
    * Contact - contact
    * Locatoin - location
    * Device model - model
    * Firmware version - firmware

You can search for VLANs straight with *-v/--find-vlan TAG* option.
To find switches with firmware older or newer than given use 
*-o/--older-software MODEL VERSION* or *-n/--newer-software MODEL VERSION* 
respectively.
To find switches with firmware version older than newest one in DB use
*-t/--outdated* option.

### Show

*-S Group*
To show all records in short use *-a/--all* key. To show full output on one
record use *-d/--device DEVICE* where value can be an IPv4 address or FQDN. To show
switches considered inactive (not contacted last time) use *-i/--inactive* key.


### Generate

*-G group*
Generate usefull info from DB records. To generate a TACACS+ allowed\_hosts list
for before.sh script use *--tacacs* key.
