import random
import time
import configparser
import psutil
import os
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
OVERALL_RUN = 1
DEBUG_GDB = False
PLATOONS = 4
NODES_PER_PLATOON = 5
RUN_NUMBER_VALS = range(0, 5)
LOSS_RATE_DISCONNECTED = 100
LOSS_RATE_CONNECTED = 10

PROTO = "svs"
#PROTO = "syncps"

APP_EXECUTABLE = None
UAV_EXECUTABLE = None

if PROTO == "svs":
    APP_EXECUTABLE = "/home/vagrant/svs-pubsub-eval/svs-client/SVSClient"
    UAV_EXECUTABLE = "/home/vagrant/svs-pubsub-eval/svs-client/SVSUAV"
elif PROTO == "syncps":
    APP_EXECUTABLE = "/home/vagrant/svs-pubsub-eval/svs-client/SyncpsClient"
    UAV_EXECUTABLE = "/home/vagrant/svs-pubsub-eval/svs-client/SyncpsUAV"

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
        access_points.append(topo.addHost('ap{}'.format(i)))
        topo.addLink(uav, access_points[i], delay='10ms')

        for j in range(0, NODES_PER_PLATOON):
            unit = topo.addHost('unit_{}_{}'.format(i, j))
            topo.addLink(access_points[i], unit, delay='10ms')
            units.append(unit)

    ndn = Minindn(topo=topo, controller=OVSController)

    ndn.start()

    info('Starting NFD on nodes\n')
    nfds = AppManager(ndn, ndn.net.hosts, Nfd)
    info('Sleeping 4 seconds\n')
    time.sleep(3 if DEBUG_GDB else 4)

    info('Setting NFD strategy to multicast on all nodes with prefix')
    for node in tqdm(ndn.net.hosts):
        Nfdc.setStrategy(node, "/ndn/", Nfdc.STRATEGY_MULTICAST)
        Nfdc.setStrategy(node, "/voice/", Nfdc.STRATEGY_MULTICAST)

    info('Adding static routes to NFD\n')
    start = int(time.time() * 1000)

    print(units[0])

    grh = NdnRoutingHelper(ndn.net, 'udp', 'link-state')
    # Add /ndn and /voice prefix to the UAV and to all units
    grh.addOrigin([ndn.net["uav"]], ["/ndn", "/voice"])
    for unit in units:
        grh.addOrigin([ndn.net[unit]], ["/ndn", "/voice"])

    grh.calculateNPossibleRoutes()

    end = int(time.time() * 1000)
    info('Added static routes to NFD in {} ms\n'.format(end - start))
    info('Sleeping 4 seconds\n')
    time.sleep(3 if DEBUG_GDB else 4)

    #all_nodes = [ndn.net[unit] for unit in units] + [ndn.net["uav"]]
    #AppManager(ndn, all_nodes, PingServer)
    # print("\n--- Link from UAV to AP3 should be the only one that is connected, try the following to verify ---")
    # print("uav ndnping -o 1000 -i 500 -c 10 -p $(openssl rand -hex 10) /ndn/platoon3/unit1")
    # print("uav ndnping -o 1000 -i 500 -c 10 -p $(openssl rand -hex 10) /ndn/platoon0/unit1")
    # MiniNDNCLI(ndn.net)

    for run_number in RUN_NUMBER_VALS:
        # Set globals
        RUN_NUMBER = run_number

        # Clear content store
        for node in ndn.net.hosts:
            cmd = 'nfdc cs erase /'
            node.cmd(cmd)

            with open("{}/report-start-{}.status".format(getLogPath(), node.name), "w") as f:
                f.write(node.cmd('nfdc status report'))

        time.sleep(1)

        random.seed(RUN_NUMBER)

        info('UAV initially connects to AP0\n')
        connect_to_ap(ndn.net, 0)

        info('Start units and UAV\n')
        AppManager(ndn, [ndn.net[unit] for unit in units], PlatoonClient)
        AppManager(ndn, [ndn.net["uav"]], UAVClient)

        current_link = 0
        for i in range(0, 10):
            connect_to_ap(ndn.net, current_link)
            current_link = (current_link + 1) % PLATOONS
            time.sleep(3)

        # kill all
        os.system('pkill ' + APP_EXECUTABLE.split('/')[-1])
        os.system('pkill ' + UAV_EXECUTABLE.split('/')[-1])
        time.sleep(3)

        for node in ndn.net.hosts:
            with open("{}/report-end-{}.status".format(getLogPath(), node.name), "w") as f:
                f.write(node.cmd('nfdc status report'))

    ndn.stop()
