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

from mininet.log import setLogLevel, info
from minindn.wifi.minindnwifi import MinindnWifi
from minindn.util import MiniNDNWifiCLI, getPopen
from minindn.apps.app_manager import AppManager
from minindn.apps.nfd import Nfd
from minindn.helpers.nfdc import Nfdc
from minindn.helpers.ndnping import NDNPing
from time import sleep
from mn_wifi.link import WirelessLink, adhoc, wmediumd
from mn_wifi.wmediumdConnector import interference

# ======================= CONFIGURATION ============================
OVERALL_RUN = 47
PLATOONS = 4
NODES_PER_PLATOON = 5
LOSS_RATE_DISCONNECTED = 100
LOSS_RATE_CONNECTED = 1
SWITCH_TIME = 30
NUM_ROUNDS = 2  # (while publishing)
# 3 rounds after stop publish

STATUS_LOG_INTERVAL_MS = 500
RUN_NUMBER_VALS = range(0, 1)
DEBUG_GDB = False

NFD_SLEEP_TIME = 2

#PROTO = "svs"
#PROTO = "syncps"
PROTO = "ip"

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

    ndn = MinindnWifi(link=wmediumd, wmediumd_mode=interference)

    uav = ndn.net["uav"]
    uav.coord = ['400,800,0',
                 '800,800,0', '800,200,0', '200,200,0', '200,800,0', '400,800,0',
                 '800,800,0', '800,200,0', '200,200,0', '200,800,0', '400,800,0',
                 '800,800,0', '800,200,0', '200,200,0', '200,800,0', '400,800,0',
                 '800,800,0', '800,200,0', '200,200,0', '200,800,0', '400,800,0',
                 '800,800,0', '800,200,0', '200,200,0', '200,800,0', '400,800,0']

    ndn.net.mobility(uav, 'start', time=0, position=uav.coord[0])
    ndn.net.mobility(uav, 'stop', time=SWITCH_TIME*4*5, position=uav.coord[-1])

    ndn.net.setPropagationModel(model="friis")

    ndn.net.stopMobility(time=SWITCH_TIME*4*5)
    ndn.startMobility(time=0, draw=False)

    info('Starting NFD on nodes\n')
    nfds = AppManager(ndn, ndn.net.stations, Nfd)
    info('Sleeping {} seconds\n'.format(NFD_SLEEP_TIME))
    time.sleep(NFD_SLEEP_TIME)

    info('Setting NFD strategy to multicast on all nodes with prefix')
    for node in tqdm(ndn.net.stations):
        Nfdc.setStrategy(node, "/ndn/", Nfdc.STRATEGY_MULTICAST)
        Nfdc.setStrategy(node, "/voice/", Nfdc.STRATEGY_MULTICAST)

        ln = [k.strip() for k in node.cmd('nfdc status report').split('\n') if 'faceid=' in k and 'wlan0' in k and 'dev://' in k][0]
        faceid = ((ln.split(' ')[0]).split('='))[1]
        print(faceid)
        node.cmd("nfdc route add prefix /ndn nexthop " + faceid)
        node.cmd("nfdc route add prefix /voice nexthop " + faceid)

    START_TIME = 0

    def writeStatus(prefix):
        for node in ndn.net.stations:
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
        for node in ndn.net.stations:
            ndn.net.addLink(node, cls=adhoc, intf=node.name+'-wlan0', ssid='adhocNet')

            if PROTO != 'ip':
                cmd = 'nfdc cs erase /'
                node.cmd(cmd)

        writeStatus('start')

        random.seed(RUN_NUMBER)

        info('UAV initially connects to AP0\n')

        # star moving
        ndn.start()

        info('Start units and UAV\n')
        AppManager(ndn, [unit for unit in ndn.net.stations if unit.name != 'uav'], PlatoonClient)
        AppManager(ndn, [ndn.net["uav"]], UAVClient)

        current_link = 1
        for i in range(0, (NUM_ROUNDS + 3) * PLATOONS + 1):
            if i == NUM_ROUNDS * PLATOONS:
                os.system('pkill -SIGINT ' + APP_EXECUTABLE.split('/')[-1])

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

    ndn.net.stop()
    ndn.cleanUp()
