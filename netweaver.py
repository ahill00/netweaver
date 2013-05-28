import argparse
import datetime
import math
# Ignore the Paramiko warning.
import warnings
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    import paramiko
import time
import threading
import uuid


class NetWeaver(object):

    def __init__(self, source_ip, destination_name_label, destination_ip, destination_host_ip, ssh_key_path):

        self.destination_name_label = destination_name_label
        self.destination_host = destination_host_ip

        self.source_connection = paramiko.SSHClient()
        self.destination_connection = paramiko.SSHClient()
        self.source_ip = source_ip
        self.source_connection.set_missing_host_key_policy(
            paramiko.AutoAddPolicy())
        self.destination_connection.set_missing_host_key_policy(
            paramiko.AutoAddPolicy())
        self.source_connection.connect(
            source_ip, username='root', key_filename=ssh_key_path)
        self.destination_connection.connect(
            destination_host_ip, username='root', key_filename=ssh_key_path)

        trace_uuid = uuid.uuid4().__str__()
        self.pif_filename = '%s%s_pif' % (
            self.destination_name_label, trace_uuid)
        self.vif_filename = '%s%s_vif' % (
            self.destination_name_label, trace_uuid)
        self.threads = None

    def determine_vif_number(self, vif_number=0):
        """
        XenServer: vifs are named based on an interface number and domain ID. e.g., vif22.0, vif22.1
        """
        dest_cmd = 'xe vm-list name-label=%s params=dom-id --minimal' % self.destination_name_label
        dom_id = self.run_command(self.destination_connection, dest_cmd)
        return 'vif%s.%s' % (dom_id[0], vif_number)

    def pull_generated_files(self):
        ftp = self.destination_connection.open_sftp()
        ftp.chdir('/tmp/')
        ftp.get(self.vif_filename, self.vif_filename)
        ftp.get(self.pif_filename, self.pif_filename)
        ftp.close()

    def generate_and_record(self, source_command, dest_pif_cmd, dest_vif_cmd):
        if self.verify_connections():
            combined_cmd = "%s & %s" % (dest_vif_cmd, dest_pif_cmd)
            dest_thread = threading.Thread(target=self.run_command, args=(
                self.destination_connection, combined_cmd))
            dest_thread.start()
            source_thread = threading.Thread(target=self.run_command, args=(
                self.source_connection, source_command))
            source_thread.start()
            self.threads = [source_thread, dest_thread]
            return self.threads

    def run_command(self, connection, command):
        if command:
            stdin, stdout, stderr = connection.exec_command(command)
            stdin.close()
            return stdout.read().splitlines()
        else:
            return None

    def analyze(self, seq_no_col, timestamp_col, seq_no_split_by, seq_no_split_index):
        vif_capture = self.clean_file(self.vif_filename,
                                      seq_no_col, timestamp_col, seq_no_split_by, seq_no_split_index)
        pif_capture = self.clean_file(self.pif_filename,
                                      seq_no_col, timestamp_col, seq_no_split_by, seq_no_split_index)
        deltas = list()
        try:
            for key in pif_capture.keys():
                delta = vif_capture[key] - pif_capture[key]
                deltas.append(delta)
        except KeyError:
            pass

        deltas = [((delta.days * 24 * 60 * 60 + delta.seconds)
                   * 1000 + delta.microseconds / 1000) for delta in deltas]
        stat = {}
        stat['average'] = sum(deltas) / float(len(deltas))
        stat['minimum'] = min(deltas)
        stat['maximum'] = max(deltas)
        variance = [(delta - stat['average'])**2 for delta in deltas]
        stat['stdev'] = math.sqrt(sum(variance) / float(len(variance)))
        return stat

    def clean_file(self, filepath, seq_no_col, timestamp_col, seq_no_split_by, seq_no_split_index):
        # normalize the files on timestamp and sequence number.
        file = open(filepath, 'r')
        cleansed_output = dict()
        for line in file:
            lineparts = line.split(' ')
            try:
                if seq_no_split_by:
                    sequence = lineparts[seq_no_col].split(
                        seq_no_split_by)[seq_no_split_index]
                else:
                    sequence = lineparts[seq_no_col]
            except IndexError:
                continue
            timestamp = lineparts[timestamp_col]
            cleansed_output[sequence] = times = datetime.datetime.strptime(
                timestamp, "%H:%M:%S.%f")
        file.close()
        return cleansed_output

    def verify_connections(self):
        source = self.run_command(self.source_connection, 'w; hostname')
        dest = self.run_command(self.destination_connection, 'w; hostname')
        if source and dest:
            return True
        else:
            return False

if __name__ == "__main__":
    usage = """python netweaver.py [-s source_ip] [-d destination_ip] [-h destination_hypervisor] [-n destination_name_label] [-k key_path]"""
    parser = argparse.ArgumentParser('netweaver.py')
    parser.add_argument('-s', dest='source_ip')
    parser.add_argument('-d', dest='destination_ip')
    parser.add_argument('--hv', dest='dom0_ip')
    parser.add_argument('-n', dest='destination_name_label')
    parser.add_argument('--num', dest='vif_num', default='0')
    parser.add_argument('-i', dest='host_interface', default='eth0')
    parser.add_argument('-k', dest='key_path')
    options = parser.parse_args()

    weaver = NetWeaver(
        options.source_ip, options.destination_name_label, options.destination_ip, options.dom0_ip, options.key_path)

    source_command = 'hping3 -c 1000 -S -L 0 --fast %s' % (
        options.destination_ip)
    weaver.verify_connections()

    destination_vif = weaver.determine_vif_number(options.vif_num)

    source_command = 'hping3 -c 1000 -S -L 0 -Q --fast %s' % (
        options.destination_ip)

    destination_pif_cmd = 'tcpdump -tttt -nnni %s -c 1000 src host %s and dst host %s | tee /tmp/%s' % (
        options.host_interface, options.source_ip, options.destination_ip, weaver.pif_filename)
    destination_vif_cmd = 'tcpdump -tttt -nnni %s -c 1000 src host %s and dst host %s | tee /tmp/%s' % (
        destination_vif, options.source_ip, options.destination_ip, weaver.vif_filename)

    print "Spawning packet captures..."
    main_threads = weaver.generate_and_record(
        source_command, destination_pif_cmd, destination_vif_cmd)
    for thread in main_threads:
        thread.join()
    print "Captures finished, waiting for files to flush."
    time.sleep(5)
    print "Transferring files..."
    weaver.pull_generated_files()
    # See README on packet analysis
    print weaver.analyze(seq_no_col=7, timestamp_col=1, seq_no_split_by=':', seq_no_split_index=0)
