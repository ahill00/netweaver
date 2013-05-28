NetWeaver
===

Measure virtual networking performance with varying traffic patterns and underlying configurations.


Requirements
==

* XenServer 5.6 or greater; easily extended to other hypervisors by overriding `determine_vif_number()`
* Key based root SSH to destination hypervisor
* Specific root SSH key in authorized_keys on source VM

- - - 

Getting Started
==

Example usage:

	python netweaver.py
	-n instance-<uuid> \
	--hv <hv_ip> \
	-s <source_ip> \
	-i <host interface|default: eth0> \
	--num <vif num|default: 0> \
	-d <destination_ip> \
	-k <keyfile>
	Spawning packet captures...
	Captures finished, waiting for files to flush.
	Transferring files...
	{'average': 21.174698795180724, 'minimum': 0, 'maximum': 514, 'stdev': 50.798123981202764}

Most options are self explanatory. `--num` refers to x in `vif1.x`… most single nic VMs will only have a `vif1.0`, each additional vif gets that 0 incremented.

The numbers output are in microseconds.
- - - 

Details
===
`source_command` runs in all source VMs. It should be a command that generates a specific traffic pattern that has an end. For example:

	source_command = 'hping3 -c 10000 -S -L 0 -Q --fast %s' % (destination_ip)

While `source_command` runs, two other commands will run on the destination VM's hypervisor to analyze the physical interface and vif traffic. The difference in the timestamps on the vif and the physical device is the overhead by various components.

`destination_pif_cmd` and `destination_vif_cmd`. These commands should have the same duration as `source_command` and be extremely verbose in their timestamp reporting. For example:

	destination_pif_cmd = 'tcpdump -tttt -nnni %s -w /tmp/destination_uuid_pif -c10000 %s src host %s and dst host %s' % (host_interface, source_ip, destination_ip, output)

	destination_vif_cmd = 'tcpdump -tttt -nnni %s -w /tmp/destination_uuid_vif -c10000 %s src host %s and dst host %s' % (vif, source_ip, destination_ip, output)

You also need to know what sort of packet your `source_command` produces. The `source_command` in the example produces this:

	2013-05-21 20:53:56.421831 IP 192.168.1.2.2911 > 192.168.1.1.0: S 36550021:36550021(0) win 512

The call to `analyze()` requires the following parameters: 

* `seq_no_col` : packet sequence number column (starting from 0 -(#7 in the example packet)
* `timestamp_col` : timestamp column (starting from 0 - #1 in the example packet)
* `seq_no_split_by` : split sequence number by (':' in the example packet)
* `seq_no_split_index` : sequence number split index (starting from 0 - 0 in the example packet)

The result is that weaver will say packet #36550021 came into eth0 at 20:53:56.421831. It then measures the amount of time it took for packet #36550021 to arrive on the vif.