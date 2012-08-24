#!/usr/bin/python
import argparse
import os
import subprocess
import sys
import yaml
import time

head = ''
clients = ''
servers = ''
mons = ''
rgws = ''
iterations = sys.maxint
rebuild_every_test = False
user = 'nhm'

def get_nodes(nodes):
    seen = {}
    ret = ''
    for node in nodes:
        if node and not node in seen:
            if ret:
                ret += ','
            ret += '%s' % node
            seen[node] = True
    print ret
#    ret = ','.join(set(ret.split(',')))
#    print ret
    return ret

def pdsh(nodes, command):
    args = ['pdsh', '-R', 'ssh', '-w', nodes, command]
    print('pdsh: %s' % args)
    return subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def pdcp(nodes, flags, localfile, remotefile):
    args = ['pdcp', '-R', 'ssh', '-w', nodes, localfile, remotefile]
    if flags:
        args = ['pdcp', '-R', 'ssh', '-w', nodes, flags, localfile, remotefile]
    return subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def rpdcp(nodes, flags, remotefile, localfile):
    args = ['rpdcp', '-R', 'ssh', '-w', nodes, remotefile, localfile]
    if flags:
        args = ['rpdcp', '-R', 'ssh', '-w', nodes, flags, remotefile, localfile]
    return subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def read_config(config_file):
    config = {}
    try:
        with file(config_file) as f:
            g = yaml.safe_load_all(f)
            for new in g:
                config.update(new)
    except IOError, e:
        raise argparse.ArgumentTypeError(str(e))
    return config

def check_health():
    print 'Waiting until Ceph is healthy...'
    while True:
        stdout, stderr = pdsh(head, 'ceph health').communicate()
        if "HEALTH_OK" in stdout:
            break
        else:
            print stdout
        time.sleep(1)

def make_remote_dir(remote_dir):
    print 'Making remote directory: %s' % remote_dir
    pdsh(get_nodes([clients,servers,mons,rgws]), 'mkdir -p -m0755 -- %s' % remote_dir).communicate()

def sync_files(tmp_dir, out_dir):
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)
    rpdcp(get_nodes([clients,servers,mons,rgws]), '-r', tmp_dir, out_dir).communicate()

def setup_cluster(config, tmp_dir):
    global head, clients, servers, mons, rgws, fs, iterations, rebuild_every_test
    print "Setting up cluster..."
    head = config.get('head', '')
    clients = config.get('clients', '')
    rgws = config.get('rgws', '')
    servers = config.get('servers', '')
    mons = config.get('mons', '')
    fs = config.get('filesystem', 'btrfs')
    iterations = config.get('iterations', sys.maxint)
    config_file = config.get('ceph.conf', '/etc/ceph/ceph.conf')
    rebuild_every_test = config.get('rebuild_every_test', False)
    print "Stoping monitoring."
    stop_monitoring()
    print "Stopping ceph."
    stop_ceph()
    print 'Deleting %s' % tmp_dir
    pdsh(get_nodes([clients,servers,mons,rgws]), 'rm -rf %s' % tmp_dir_base).communicate()

    print "Distributing %s." % config_file
    setup_ceph_conf(config_file)

def setup_ceph(config):
    print "Stoping monitoring."
    stop_monitoring()
    print "Stopping ceph."
    stop_ceph()
    print "Deleting old ceph logs."
    purge_logs()
    print "Deleting old mon data."
    pdsh(mons, 'sudo rm -rf /var/lib/ceph/mon/*').communicate()
    print "Building the underlying OSD filesystem"
    setup_fs(config)
    print 'Running mkcephfs.'
    mkcephfs()
    print 'Starting Ceph.'
    start_ceph()
    print 'Setting up pools'
    setup_pools()
    if rgws:
        print 'Creating rgw users.'
        setup_rgw()
        print 'Downloading s3-tests.'
        setup_s3tests(tmp_dir)
    check_health()

def shutdown(message):
    print "Stopping monitoring."
    stop_monitoring()
    print "Stopping ceph."
    stop_ceph()
    sys.exit(message)

def purge_logs():
    pdsh(get_nodes([clients, servers, mons, rgws]), 'sudo rm -rf /var/log/ceph/*').communicate()

def make_movies(tmp_dir):
    seekwatcher = '/home/%s/bin/seekwatcher' % user
    blktrace_dir = '%s/blktrace' % tmp_dir
    pdsh(servers, 'cd %s;%s -t device0 -o device0.mpg --movie' % (blktrace_dir,seekwatcher)).communicate()
    pdsh(servers, 'cd %s;%s -t journal0 -o journal0.mpg --movie' % (blktrace_dir,seekwatcher)).communicate()
    pdsh(servers, 'cd %s;%s -t device1 -o device1.mpg --movie' % (blktrace_dir,seekwatcher)).communicate()
    pdsh(servers, 'cd %s;%s -t journal1 -o journal1.mpg --movie' % (blktrace_dir,seekwatcher)).communicate()
    pdsh(servers, 'cd %s;%s -t device2 -o device2.mpg --movie' % (blktrace_dir,seekwatcher)).communicate()
    pdsh(servers, 'cd %s;%s -t journal2 -o journal2.mpg --movie' % (blktrace_dir,seekwatcher)).communicate()
    pdsh(servers, 'cd %s;%s -t device3 -o device3.mpg --movie' % (blktrace_dir,seekwatcher)).communicate()
    pdsh(servers, 'cd %s;%s -t journal3 -o journal3.mpg --movie' % (blktrace_dir,seekwatcher)).communicate()
    pdsh(servers, 'cd %s;%s -t device4 -o device4.mpg --movie' % (blktrace_dir,seekwatcher)).communicate()
    pdsh(servers, 'cd %s;%s -t journal4 -o journal4.mpg --movie' % (blktrace_dir,seekwatcher)).communicate()
    pdsh(servers, 'cd %s;%s -t device5 -o device5.mpg --movie' % (blktrace_dir,seekwatcher)).communicate()
    pdsh(servers, 'cd %s;%s -t journal5 -o journal5.mpg --movie' % (blktrace_dir,seekwatcher)).communicate()

def perf_post(tmp_dir):
    perf_dir = '%s/perf' % tmp_dir
    pdsh(get_nodes([clients, servers, mons, rgws]), 'cd %s;sudo chown %s.%s perf.data' % (perf_dir, user, user)).communicate()
#    pdsh('%s,%s,%s,%s' % (clients, servers, mons, rgws), 'cd %s;perf_3.4 report --sort symbol --call-graph fractal,5 > callgraph.txt' % perf_dir).communicate()

def start_monitoring(tmp_dir):
    collectl_dir = '%s/collectl' % tmp_dir
    perf_dir = '%s/perf' % tmp_dir
    blktrace_dir = '%s/blktrace' % tmp_dir

    # collectl
    pdsh(get_nodes([clients, servers, mons, rgws]), 'mkdir -p -m0755 -- %s;collectl -s+YZ -i 1:10 -F0 -f %s' % (collectl_dir,collectl_dir))

    # perf
    pdsh(get_nodes([clients, servers, mons, rgws]), 'mkdir -p -m0755 -- %s' % perf_dir).communicate()
    pdsh(get_nodes([clients, servers, mons, rgws]), 'cd %s;sudo perf_3.4 record -g -f -a -F 100 -o perf.data' % perf_dir)

    # blktrace
    pdsh(servers, 'mkdir -p -m0755 -- %s' % blktrace_dir).communicate()
    pdsh(servers, 'cd %s;sudo blktrace -o device0 -d /dev/disk/by-partlabel/osd-device-0-data' % blktrace_dir)
    pdsh(servers, 'cd %s;sudo blktrace -o journal0 -d /dev/disk/by-partlabel/osd-device-0-journal' % blktrace_dir)
    pdsh(servers, 'cd %s;sudo blktrace -o device1 -d /dev/disk/by-partlabel/osd-device-1-data' % blktrace_dir)
    pdsh(servers, 'cd %s;sudo blktrace -o journal1 -d /dev/disk/by-partlabel/osd-device-1-journal' % blktrace_dir)
    pdsh(servers, 'cd %s;sudo blktrace -o device2 -d /dev/disk/by-partlabel/osd-device-2-data' % blktrace_dir)
    pdsh(servers, 'cd %s;sudo blktrace -o journal2 -d /dev/disk/by-partlabel/osd-device-2-journal' % blktrace_dir)
    pdsh(servers, 'cd %s;sudo blktrace -o device3 -d /dev/disk/by-partlabel/osd-device-3-data' % blktrace_dir)
    pdsh(servers, 'cd %s;sudo blktrace -o journal3 -d /dev/disk/by-partlabel/osd-device-3-journal' % blktrace_dir)
    pdsh(servers, 'cd %s;sudo blktrace -o device4 -d /dev/disk/by-partlabel/osd-device-4-data' % blktrace_dir)
    pdsh(servers, 'cd %s;sudo blktrace -o journal4 -d /dev/disk/by-partlabel/osd-device-4-journal' % blktrace_dir)
    pdsh(servers, 'cd %s;sudo blktrace -o device5 -d /dev/disk/by-partlabel/osd-device-5-data' % blktrace_dir)
    pdsh(servers, 'cd %s;sudo blktrace -o journal5 -d /dev/disk/by-partlabel/osd-device-5-journal' % blktrace_dir)

def stop_monitoring():
    pdsh(get_nodes([clients,servers,mons,rgws]), 'pkill -SIGINT -f collectl').communicate()
    pdsh(get_nodes([clients,servers,mons,rgws]), 'sudo pkill -SIGINT -f perf_3.4').communicate()
    pdsh(servers, 'sudo pkill -SIGINT -f blktrace').communicate()

def start_ceph():
    pdsh(get_nodes([clients,servers,mons,rgws]), 'sudo /etc/init.d/ceph start').communicate()
    if rgws:
        pdsh(rgws, 'sudo /etc/init.d/radosgw start;sudo /etc/init.d/apache2 start').communicate()

def stop_ceph():
    pdsh(get_nodes([clients,servers,mons,rgws]), 'sudo /etc/init.d/ceph stop').communicate()
    if rgws:
        pdsh(rgws, 'sudo /etc/init.d/radosgw stop;sudo /etc/init.d/apache2 stop').communicate()

def setup_ceph_conf(conf_file):
    pdcp(get_nodes([head,clients,servers,mons,rgws]), '', conf_file, '/tmp/ceph.conf').communicate()
    pdsh(get_nodes([head,clients,servers,mons,rgws]), 'sudo cp /tmp/ceph.conf /etc/ceph/ceph.conf').communicate()

def mkcephfs():
    pdsh(head, 'sudo mkcephfs -a -c /etc/ceph/ceph.conf').communicate()

def setup_fs(config):
    fs = config.get('fs', 'btrfs')
    mkfs_opts = config.get('mkfs_opts', '')
    mount_opts = config.get('mount_opts', '-o noatime')
    osds_per_node = config.get('osds_per_node', 1)

    if fs == '':
        shutdown("No OSD filesystem specified.  Exiting.")

    for device in xrange (0,osds_per_node):
        pdsh(servers, 'sudo umount /srv/osd-device-%s-data;sudo rm -rf /srv/osd-device-%s' % (device, device)).communicate()
        pdsh(servers, 'sudo mkdir /srv/osd-device-%s-data' % device).communicate()
        pdsh(servers, 'sudo mkfs.%s %s /dev/disk/by-partlabel/osd-device-%s-data' % (fs, mkfs_opts, device)).communicate()
        pdsh(servers, 'sudo mount %s -t %s /dev/disk/by-partlabel/osd-device-%s-data /srv/osd-device-%s-data' % (mount_opts, fs, device, device)).communicate()

def setup_rgw():
    pdsh(rgws, 'sudo radosgw-admin user create --uid user --display_name user --access-key test --secret \'dGVzdA==\' --email test@test.test').communicate()
    pdsh(rgws, 'sudo radosgw-admin user create --uid user2 --display_name user2 --access-key test2 --secret \'dGVzdDI=\' --email test@test.test').communicate()

def setup_pools():
    pdsh(head, 'sudo ceph osd pool create rest-bench 1024 1024').communicate()
    pdsh(head, 'sudo ceph osd pool set rest-bench size 1').communicate()
    pdsh(head, 'sudo ceph osd pool create rados-bench 1024 1024').communicate()
    pdsh(head, 'sudo ceph osd pool set rados-bench size 1').communicate()
    if rgws:
        pdsh(rgws, 'sudo radosgw-admin -p rest-bench pool add').communicate()
        pdsh(rgws, 'sudo radosgw-admin -p .rgw.buckets pool rm').communicate()

def setup_s3tests(tmp_dir):
    pdsh(clients, 'sudo apt-get update').communicate()
    pdsh(clients, 'sudo apt-get install libyaml-dev').communicate()
    pdsh(clients, 'rm -rf %s/s3-tests' % tmp_dir).communicate()
    pdsh(clients, 'mkdir -p -m0755 -- %s' % tmp_dir).communicate()
    pdsh(clients, 'git clone http://ceph.newdream.net/git/s3-tests.git %s/s3-tests' % tmp_dir).communicate()
    pdsh(clients, 'cd %s/s3-tests;./bootstrap' % tmp_dir).communicate()
    pdcp(clients, '-r', 'conf', '%s/s3-tests' % tmp_dir).communicate()

def cleanup_tests():
    pdsh(clients, 'sudo pkill -f rados;sudo pkill -f rest-bench').communicate()
    if rgws:
        pdsh(rgws, 'sudo pkill -f radosgw-admin').communicate()
    pdsh(get_nodes([clients, servers, mons, rgws]), 'sudo pkill -f pdcp').communicate()

def run_radosbench(config, tmp_dir, archive_dir):
    print 'Running radosbench tests...'

    time = str(config.get('time', '360'))
    pool = str(config.get('pool', ''))
    if pool: pool = '-p %s' % pool

    # Get the concurrent ops 
    concurrent_ops_array = config.get('concurrent_ops', [16])

    op_sizes = config.get('op_sizes', [4194304])
    for op_size in op_sizes:
        for concurrent_ops in concurrent_ops_array:
            # Rebuild the cluster if set
            if rebuild_every_test:
                setup_ceph(cluster_config)

            run_dir = '%s/radosbench/op_size-%08d/concurrent_ops-%08d' % (tmp_dir, int(op_size), int(concurrent_ops))
            out_dir = '%s/radosbench/op_size-%08d/concurrent_ops-%08d' % (archive_dir, int(op_size), int(concurrent_ops))

            # set the concurrent_ops if specified in yaml
            if concurrent_ops:
                concurrent_ops_str = '--concurrent-ios %s' % concurrent_ops

            make_remote_dir(run_dir)
            out_file = '%s/output' % run_dir
            objecter_log = '%s/objecter.log' % run_dir
            op_size_str = '-b %s' % op_size
            start_monitoring(run_dir)
            stdout, stderr = pdsh(clients, '/usr/bin/rados %s %s bench %s write %s 2> %s > %s' % (pool, op_size_str, time, concurrent_ops_str, objecter_log, out_file)).communicate()
            print stdout
            print stderr
            stop_monitoring()
            perf_post(run_dir)
            make_movies(run_dir)
            sync_files('%s/*' % run_dir, out_dir)
    print 'Done.'

def run_restbench(config, tmp_dir, archive_dir):
    print 'Running rest-bench tests...'

    time = str(config.get('time', '360'))
    time = '--seconds=%s' % time
    concurrent_ops = str(config.get('concurrent_ops', ''))
    if concurrent_ops: concurrent_ops = '-t %s' % concurrent_ops
    bucket = str(config.get('bucket', ''))
    if bucket: bucket = '--bucket=%s' % bucket
    access_key = str(config.get('access_key', ''))
    if access_key: access_key = '--access-key=%s' % access_key
    secret = str(config.get('secret', ''))
    if secret: secret = '--secret=%s' % secret
    api_host = str(config.get('api_host', ''))
    if api_host: api_host = '--api-host=%s' % api_host

    op_sizes = config.get('op_sizes', [])

    for op_size in op_sizes:
        # Rebuild the cluster if set
        if rebuild_every_test:
            setup_ceph(cluster_config)

        run_dir = '%s/rest-bench/op_size-%08d' % (tmp_dir, op_size)
        out_dir = '%s/rest-bench/op_size-%08d' % (archive_dir, op_size)
        make_remote_dir(run_dir)
        out_file = '%s/output' % run_dir
        op_size = '-b %s' % op_size

        start_monitoring(run_dir)
	pdsh(clients, '/usr/bin/rest-bench %s %s %s %s %s %s %s write > %s' % (api_host, access_key, secret, concurrent_ops, op_size, time, bucket, out_file)).communicate()
        stop_monitoring()
        perf_post(run_dir)
        make_movies(run_dir)
        sync_files('%s/*' % run_dir, out_dir)
    print 'Done.'


def run_s3rw(config, tmp_dir, archive_dir):
    print 'Running s3rw tests...'

    config_files = config.get('config_files', [])
    for config_file in config_files:
        short_name = config_file.rpartition('/')[2]
        run_dir = '%s/s3rw/%s' % (tmp_dir, short_name)
        out_dir = '%s/s3rw/%s' % (archive_dir, short_name)

        make_remote_dir(run_dir)
        out_file = '%s/output' % run_dir 
        start_monitoring(run_dir)
        pdsh(clients, '%s/s3-tests/virtualenv/bin/s3tests-test-readwrite < %s > %s' % (tmp_dir, config_file, out_file)).communicate()
        stop_monitoring()
        make_movies(run_dir)
        sync_files('%s/*' % run_dir, out_dir)
    print "Done."

def run_s3func(config, tmp_dir, archive_dir):
    print 'Running s3func tests...'
    
    config_files = config.get('config_files', [])
    for config_file in config_files:
        short_name = config_file.rpartition('/')[2]
        run_dir = '%s/s3func/%s' % (tmp_dir, short_name)
        out_dir = '%s/s3func/%s' % (archive_dir, short_name)

        make_remote_dir(run_dir)
        out_file = '%s/output' % run_dir 
        start_monitoring(run_dir)
        pdsh(clients, 'export S3TEST_CONF=%s;cd /tmp/cephtest/s3-tests;virtualenv/bin/nosetests -a \'!fails_on_rgw\' &> %s' % (config_file, out_file)).communicate()
        stop_monitoring()
        perf_post(run_dir)
        make_movies(run_dir)
        sync_files('%s/*' % run_dir, out_dir)
    print 'Done.'

def parse_args():
    parser = argparse.ArgumentParser(description='Continuously run ceph tests.')
    parser.add_argument(
        '--archive',
        required = True, 
        help = 'Directory where the results should be archived.',
        )
    parser.add_argument(
        'config_file',
        help = 'YAML config file.',
        )
    args = parser.parse_args()
    return args


if __name__ == '__main__':
    ctx = parse_args()
    config = read_config(ctx.config_file)
    tmp_dir_base = '/tmp/cephtest'

    iteration = 0

    cluster_config = config.get('cluster', {})
    rb_config = config.get('radosbench', {})
    restbench_config = config.get('restbench', {})
    s3func_config = config.get('s3func', {})
    s3rw_config = config.get('s3rw', {})

    if not (cluster_config):
        shutdown('No cluster section found in config file, bailing.')
    if not (rb_config or restbench_config or s3func_config or s3rw_config):
        shutdown('No task sections found in config file, bailing.')

    setup_cluster(cluster_config, tmp_dir_base)
    if not rebuild_every_test:
        setup_ceph(cluster_config)
    while iteration < iterations:
        archive_dir = os.path.join(ctx.archive, '%08d' % iteration)
        if os.path.exists(archive_dir):
            print 'Skipping existing iteration %d.' % iteration
            next
        os.makedirs(archive_dir)
        print "Cleaning up tests..."
        cleanup_tests()

        print "Running iteration %s..." % iteration
        tmp_dir = '%s/%08d' % (tmp_dir_base, iteration)
        if rb_config:
            run_radosbench(rb_config, tmp_dir, archive_dir)
        if restbench_config:
            run_restbench(restbench_config, tmp_dir, archive_dir)
        if s3func_config:
            run_s3func(s3func_config, tmp_dir, archive_dir)
        if s3rw_config:
            run_s3rw(s3rw_config, tmp_dir, archive_dir)       
        iteration += 1