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
OVERALL_RUN = 2
DEBUG_GDB = False
PLATOONS = 4
NODES_PER_PLATOON = 5
RUN_NUMBER_VALS = range(0, 5)
LOSS_RATE_DISCONNECTED = 100
LOSS_RATE_CONNECTED = 10

APP_EXEC_VALS = [
    # "/home/vagrant/mini-ndn/work/ndn-svs/build/examples/eval",          # SVS
    # "/home/vagrant/mini-ndn/work/syncps/eval",                          # syncps
]

APP_EXECUTABLE = "/home/vagrant/svs-pubsub-eval/svs-client/SVSClient"
UAV_EXECUTABLE = "/home/vagrant/svs-pubsub-eval/svs-client/SVSUAV"
#APP_EXECUTABLE = "/home/vagrant/svs-pubsub-eval/svs-client/SyncpsClient"
#UAV_EXECUTABLE = "/home/vagrant/svs-pubsub-eval/svs-client/SyncpsUAV"

LOG_MAIN_PATH = "/home/vagrant/work/log/{}/".format(OVERALL_RUN)
LOG_MAIN_DIRECTORY_VALS = [
    # LOG_MAIN_PATH + "svs/",                                       # SVS
    # LOG_MAIN_PATH + "syncps/",                                    # syncps
]
# ==================================================================

RUN_NUMBER = 0
SYNC_EXEC = None
LOG_MAIN_DIRECTORY = None


def getLogPath():
    LOG_NAME = "{}".format(RUN_NUMBER)
    logpath = LOG_MAIN_DIRECTORY + LOG_NAME

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
        run_cmd = "{} {} > log/client.out 2> log/client.err &".format(
            APP_EXECUTABLE, self.prefix)

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
        run_cmd = "{}  > log/uav.out  2> log/uav.err &".format(
            UAV_EXECUTABLE)

        ret = self.node.cmd(run_cmd)
        info("[{}] running \"{}\" == {}\n".format(
            self.node.name, run_cmd, ret))


if __name__ == '__main__':
    print(APP_EXEC_VALS)

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
    info('Sleeping 10 seconds\n')
    time.sleep(3 if DEBUG_GDB else 10)

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
    info('Sleeping 10 seconds\n')
    time.sleep(3 if DEBUG_GDB else 10)

    info('UAV initially connects to AP0\n')
    connect_to_ap(ndn.net, 0)

    info('Start units and UAV\n')
    AppManager(ndn, [ndn.net[unit] for unit in units], PlatoonClient)
    AppManager(ndn, [ndn.net["uav"]], UAVClient)
    #all_nodes = [ndn.net[unit] for unit in units] + [ndn.net["uav"]]
    #AppManager(ndn, all_nodes, PingServer)

    current_link = 0
    for i in range(0, 10):
        connect_to_ap(ndn.net, current_link)
        current_link = (current_link + 1) % PLATOONS
        time.sleep(30)

    # time.sleep(2)
    # connect_to_ap(ndn.net, 0)
    # time.sleep(2)
    # connect_to_ap(ndn.net, 1)
    # time.sleep(2)
    # connect_to_ap(ndn.net, 2)
    # time.sleep(2)
    # connect_to_ap(ndn.net, 3)

    # print("\n--- Link from UAV to AP3 should be the only one that is connected, try the following to verify ---")
    # print("uav ndnping -o 1000 -i 500 -c 10 -p $(openssl rand -hex 10) /ndn/platoon3/unit1")
    # print("uav ndnping -o 1000 -i 500 -c 10 -p $(openssl rand -hex 10) /ndn/platoon0/unit1")
    # MiniNDNCLI(ndn.net)

    # for exec_i, app_exec in enumerate(APP_EXEC_VALS):
    #     for run_number in RUN_NUMBER_VALS:
    #         # Set globals
    #         RUN_NUMBER = run_number
    #         APP_EXEC = app_exec
    #         LOG_MAIN_DIRECTORY = LOG_MAIN_DIRECTORY_VALS[exec_i]

    #         # Clear content store
    #         for node in ndn.net.hosts:
    #             cmd = 'nfdc cs erase /'
    #             node.cmd(cmd)

    #             with open("{}/report-start-{}.status".format(getLogPath(), node.name), "w") as f:
    #                 f.write(node.cmd('nfdc status report'))

    #         time.sleep(1)

    #         random.seed(RUN_NUMBER)
    #         allowed_hosts = [x for x in ndn.net.hosts if len(x.intfList()) < 8]
    #         pub_hosts = random.sample(allowed_hosts, NUM_NODES)

    #         # ================= SVS BEGIN ====================================

    #         # identity_app = AppManager(ndn, pub_hosts, IdentityApplication)
    #         svs_chat_app = AppManager(ndn, pub_hosts, SvsChatApplication)

    #         # =================== SVS END ====================================

    #         pids = get_pids()
    #         info("pids: {}\n".format(pids))
    #         count = count_running(pids)
    #         while count > 0:
    #             info("{} nodes are runnning\n".format(count))
    #             time.sleep(5)
    #             count = count_running(pids)

    #         for node in ndn.net.hosts:
    #             with open("{}/report-end-{}.status".format(getLogPath(), node.name), "w") as f:
    #                 f.write(node.cmd('nfdc status report'))

    ndn.stop()

    print(APP_EXEC_VALS)
