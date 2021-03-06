import common
import settings
import subprocess

def start(directory):
    sc = settings.cluster
    nodes = common.get_nodes([sc.get('clients'), sc.get('servers'), sc.get('mons'), sc.get('rgws')])
    collectl_dir = '%s/collectl' % directory
    perf_dir = '%s/perf' % directory
    blktrace_dir = '%s/blktrace' % directory

    # collectl
    common.pdsh(nodes, 'mkdir -p -m0755 -- %s;collectl -s+mYZ -i 1:10 -F0 -f %s' % (collectl_dir,collectl_dir))

    # perf
#    common.pdsh(get_nodes([clients, servers, mons, rgws]), 'mkdir -p -m0755 -- %s' % perf_dir).communicate()
#    common.pdsh(get_nodes([clients, servers, mons, rgws]), 'cd %s;sudo perf_3.6 record -g -f -a -F 100 -o perf.data' % perf_dir)

    # blktrace
#    common.pdsh(servers, 'mkdir -p -m0755 -- %s' % blktrace_dir).communicate()
#    for device in xrange (0,osds_per_node):
#        common.pdsh(servers, 'cd %s;sudo blktrace -o device%s -d /dev/disk/by-partlabel/osd-device-%s-data' % (blktrace_dir, device, device))



def stop(directory=None):
    sc = settings.cluster
    nodes = common.get_nodes([sc.get('clients'), sc.get('servers'), sc.get('mons'), sc.get('rgws')])
    common.pdsh(nodes, 'pkill -SIGINT -f collectl').communicate()
    common.pdsh(nodes, 'sudo pkill -SIGINT -f perf_3.6').communicate()
    common.pdsh(sc.get('servers'), 'sudo pkill -SIGINT -f blktrace').communicate()
    if directory:
        common.pdsh(nodes, 'cd %s/perf;sudo chown %s.%s perf.data' % (directory, sc.get('user'), sc.get('user')))
        make_movies(directory)

def make_movies(directory):
    sc = settings.cluster
    seekwatcher = '/home/%s/bin/seekwatcher' % sc.get('user')
    blktrace_dir = '%s/blktrace' % directory

    for device in xrange (0,sc.get('osds_per_node')):
        common.pdsh(sc.get('servers'), 'cd %s;%s -t device%s -o device%s.mpg --movie' % (blktrace_dir,seekwatcher,device,device)).communicate()

