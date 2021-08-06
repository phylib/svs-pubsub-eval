import random
import time
import configparser
import psutil
import os
import json
from collections import defaultdict

from mininet.log import setLogLevel, info

from minindn.apps.application import Application

from minindn.helpers.nfdc import Nfdc
from mininet.topo import Topo
from minindn.minindn import Minindn
from minindn.util import MiniNDNCLI
from minindn.apps.app_manager import AppManager
from minindn.apps.nfd import Nfd
from minindn.helpers.ndn_routing_helper import NdnRoutingHelper
from mininet.node import OVSController

from tqdm import tqdm

# ======================= CONFIGURATION ============================
OVERALL_RUN = 25
PLATOONS = 4
NODES_PER_PLATOON = 5
LOSS_RATE_DISCONNECTED = 100
LOSS_RATE_CONNECTED = 10
SWITCH_TIME = 30
NUM_ROUNDS = 2  # (while publishing)
# 3 rounds after stop publish

STATUS_LOG_INTERVAL_MS = 500
RUN_NUMBER_VALS = range(0, 1)
DEBUG_GDB = False

NFD_SLEEP_TIME = 2

PROTO = "svs"
#PROTO = "syncps"
#PROTO = "ip"

APP_EXECUTABLE = None
UAV_EXECUTABLE = None

if PROTO == "svs":
    APP_EXECUTABLE = "/home/vagrant/svs-pubsub-eval/svs-client/SVSClient"
    UAV_EXECUTABLE = "/home/vagrant/svs-pubsub-eval/svs-client/SVSUAV"
elif PROTO == "syncps":
    APP_EXECUTABLE = "/home/vagrant/svs-pubsub-eval/svs-client/SyncpsClient"
    UAV_EXECUTABLE = "/home/vagrant/svs-pubsub-eval/svs-client/SyncpsUAV"
elif PROTO == "ip":
    APP_EXECUTABLE = "/home/vagrant/dtn7-go/dtnd"
    UAV_EXECUTABLE = "/home/vagrant/dtn7-go/uav"

LOG_MAIN_PATH = "/vagrant/logs/{}/".format(OVERALL_RUN)
# ==================================================================

RUN_NUMBER = 0
SYNC_EXEC = None
LOG_MAIN_DIRECTORY = LOG_MAIN_PATH

def getLogPath():
    LOG_NAME = "{}/{}/{}".format(LOG_MAIN_DIRECTORY, PROTO, RUN_NUMBER)
    logpath = LOG_NAME

    if not os.path.exists(logpath):
        os.makedirs(logpath)
        os.chown(logpath, 1000, 1000)

        os.makedirs(logpath + '/stdout')
        os.chown(logpath + '/stdout', 1000, 1000)
        os.makedirs(logpath + '/stderr')
        os.chown(logpath + '/stdout', 1000, 1000)

    return logpath


def unitname_to_name_prefix(nodename):
    """
    The units have a name that looks as follows:
    unit_{platoonid}_{nodeid}
    The NDN name of such a unit looks as follows:
    /ndn/platoon{platoonid}/unit{unitid}/
    """
    platoon_id = nodename.split('_')[1]
    unit_id = nodename.split('_')[2]
    return "/ndn/platoon{}/unit{}/".format(platoon_id, unit_id)


def set_link_loss_to(net, nodename_a, nodename_b, loss_rate):
    node_a = net[nodename_a]
    node_b = net[nodename_b]
    links = node_a.connectionsTo(node_b)
    for link in links:
        link[0].config(loss=loss_rate)
        link[1].config(loss=loss_rate)


def connect_to_ap(net, ap_number):
    info("Connect to AP{}\n".format(ap_number))
    for i in range(0, PLATOONS):
        ap_name = "ap{}".format(i)
        loss_rate = LOSS_RATE_CONNECTED if i == ap_number else LOSS_RATE_DISCONNECTED
        set_link_loss_to(net, "uav", ap_name, loss_rate)


class PingServer(Application):
    """
    Wrapper class to run the NDNPingServer on a node
    """

    def __init__(self, node):
        Application.__init__(self, node)
        self.prefix = "/ndn/{}-site/".format(node.name)

    def start(self):
        run_cmd = "ndnpingserver {0} &".format(
            self.prefix)

        ret = self.node.cmd(run_cmd)
        info("[{}] running \"{}\" == {}\n".format(
            self.node.name, run_cmd, ret))

class PlatoonClient(Application):
    """
    Wrapper class to run the PlatoonClient on a node
    """

    def __init__(self, node):
        Application.__init__(self, node)
        self.prefix = unitname_to_name_prefix(node.name)

    def start(self):
        if PROTO == "ip":
            run_cmd = "{0} {3} {2}/{3}.log :8333 store_{3} > {2}/stdout/{3}.log 2> {2}/stderr/{3}.log &".format(
                APP_EXECUTABLE, self.prefix, getLogPath(), self.node.name)
        else:
            run_cmd = "{0} {1} {2}/{3}.log > {2}/stdout/{3}.log 2> {2}/stderr/{3}.log &".format(
                APP_EXECUTABLE, self.prefix, getLogPath(), self.node.name)

        ret = self.node.cmd(run_cmd)
        info("[{}] running \"{}\" == {}\n".format(
            self.node.name, run_cmd, ret))


class UAVClient(Application):
    """
    Wrapper class to run the UAVClient on a node
    """

    def __init__(self, node):
        Application.__init__(self, node)

    def start(self):
        if PROTO == "ip":
            run_cmd = "{0} {3} {2}/{3}.log :8333 store_{3} > {2}/stdout/{3}.log 2> {2}/stderr/{3}.log &".format(
                UAV_EXECUTABLE, "/uav", getLogPath(), self.node.name)
        else:
            run_cmd = "{0} > {1}/stdout/{2}.log 2> {1}/stderr/{2}.log &".format(
                UAV_EXECUTABLE, getLogPath(), self.node.name)

        ret = self.node.cmd(run_cmd)
        info("[{}] running \"{}\" == {}\n".format(
            self.node.name, run_cmd, ret))


if __name__ == '__main__':
    setLogLevel('info')

    Minindn.cleanUp()
    Minindn.verifyDependencies()

    topo = Topo()

    # Create topology here
    uav = topo.addHost('uav')
    access_points = []
    units = []
    for i in range(0, PLATOONS):
        if PROTO == 'ip':
            access_points.append(topo.addSwitch('ap{}'.format(i)))
        else:
            access_points.append(topo.addHost('ap{}'.format(i)))

        topo.addLink(uav, access_points[i], delay='10ms')

        for j in range(0, NODES_PER_PLATOON):
            unit = topo.addHost('unit_{}_{}'.format(i, j))
            topo.addLink(access_points[i], unit, delay='10ms')
            units.append(unit)

    ndn = Minindn(topo=topo, controller=OVSController)

    ndn.start()

    # Dump IP addresses of nodes to JSON
    ips = {}
    for node in ndn.net.hosts:
        ips[node.name] = [node.IP(n) for n in node.intfList()]
    with open("{}/ips.json".format(getLogPath()), "w") as f:
        json.dump(ips, f, indent=4)
    info('Wrote IP addresses to ips.json\n')

    info('Starting NFD on nodes\n')
    nfds = AppManager(ndn, ndn.net.hosts, Nfd)
    info('Sleeping {} seconds\n'.format(NFD_SLEEP_TIME))
    time.sleep(NFD_SLEEP_TIME)

    info('Setting NFD strategy to multicast on all nodes with prefix')
    for node in tqdm(ndn.net.hosts):
        Nfdc.setStrategy(node, "/ndn/", Nfdc.STRATEGY_MULTICAST)
        Nfdc.setStrategy(node, "/voice/", Nfdc.STRATEGY_MULTICAST)

    info('Adding static routes to NFD\n')
    start = int(time.time() * 1000)

    print(units[0])

    grh = NdnRoutingHelper(ndn.net, 'udp', 'link-state')
    # Add /ndn and /voice prefix to the UAV and to all units
    grh.addOrigin([ndn.net["uav"]], ["/ndn"])
    for unit in units:
        grh.addOrigin([ndn.net[unit]], ["/ndn", "/voice"])

    if PROTO != "ip":
        grh.calculateNPossibleRoutes()

        end = int(time.time() * 1000)
        info('Added static routes to NFD in {} ms\n'.format(end - start))
        info('Sleeping {} seconds\n'.format(NFD_SLEEP_TIME))
        time.sleep(NFD_SLEEP_TIME)

    #all_nodes = [ndn.net[unit] for unit in units] + [ndn.net["uav"]]
    #AppManager(ndn, all_nodes, PingServer)
    # print("\n--- Link from UAV to AP3 should be the only one that is connected, try the following to verify ---")
    # print("uav ndnping -o 1000 -i 500 -c 10 -p $(openssl rand -hex 10) /ndn/platoon3/unit1")
    # print("uav ndnping -o 1000 -i 500 -c 10 -p $(openssl rand -hex 10) /ndn/platoon0/unit1")
    # MiniNDNCLI(ndn.net)

    START_TIME = 0

    def writeStatus(prefix):
        for node in ndn.net.hosts:
            if PROTO != 'ip':
                with open("{}/report-{}-{}.status".format(getLogPath(), prefix, node.name), "a") as f:
                    f.write("EVAL_TIME=={}\n".format(round(time.time() * 1000) - START_TIME))
                    f.write(node.cmd('nfdc status report'))
            with open("{}/report-{}-{}.ifconfig".format(getLogPath(), prefix, node.name), "a") as f:
                f.write("EVAL_TIME=={}\n".format(round(time.time() * 1000) - START_TIME))
                f.write(node.cmd('ifconfig'))

    for run_number in RUN_NUMBER_VALS:
        # Set globals
        RUN_NUMBER = run_number
        START_TIME = round(time.time() * 1000)

        # Clear content store
        for node in ndn.net.hosts:
            if PROTO != 'ip':
                cmd = 'nfdc cs erase /'
                node.cmd(cmd)

        writeStatus('start')

        time.sleep(1)

        random.seed(RUN_NUMBER)

        info('UAV initially connects to AP0\n')
        connect_to_ap(ndn.net, 0)

        info('Start units and UAV\n')
        AppManager(ndn, [ndn.net[unit] for unit in units], PlatoonClient)
        AppManager(ndn, [ndn.net["uav"]], UAVClient)

        current_link = 1
        for i in range(0, (NUM_ROUNDS + 3) * PLATOONS + 1):
            if i == NUM_ROUNDS * PLATOONS:
                os.system('pkill -SIGINT ' + APP_EXECUTABLE.split('/')[-1])

            connect_to_ap(ndn.net, current_link)
            current_link = (current_link + 1) % PLATOONS

            sleep_time = SWITCH_TIME # if i < NUM_ROUNDS * PLATOONS else 2 * SWITCH_TIME
            sleep_start = time.time()
            while time.time() < sleep_start + sleep_time:
                time.sleep(STATUS_LOG_INTERVAL_MS / 1000)
                writeStatus('eval')

        # kill all
        os.system('killall ' + APP_EXECUTABLE.split('/')[-1])
        os.system('killall ' + UAV_EXECUTABLE.split('/')[-1])
        time.sleep(3)

        writeStatus('end')

    ndn.stop()
