#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
global_cp.py: Example Contiki global control program for mac contention window optimization. Afterwards TDMA is activated. 

Usage:
   global_cp.py [options] [-q | -v]

Options:
   --logfile name      Name of the logfile
   --config configFile Config file path
   --nodes nodesFile   Config file with node info
   --measurements measurementsConfig Config file with measurement info

Example:
   python sc3_mac_cwopt/global_cp --config config/portable/global_cp_config.yaml --nodes config/portable/nodes.yaml --measurements config/portable/measurement_config.yaml

Other options:
   -h, --help          show this help message and exit
   -q, --quiet         print less text
   -v, --verbose       print more text
   --version           show version and exit
"""

import datetime
import logging
from contiki.contiki_helpers.global_node_manager import *
from contiki.contiki_helpers.taisc_manager import *
from contiki.contiki_helpers.app_manager import *
import gevent
import yaml
from measurement_logger import *

__author__ = "Peter Ruckebusch"
__copyright__ = "Copyright (c) 2016, Technische Universität Berlin"
__version__ = "0.1.0"
__email__ = "peter.ruckebusch@intec.ugent.be"


def calculateCWOpt(num_tx_nodes):
    # constants
    MacHdrLen = 11  # num mac hdr bytes
    MackAckLen = 6  # num ack bytes
    N_aMaxSIFSFrameSize = 18
    N_aUnitBackoffPeriod = 20  # num symbols in base backoff period
    T_Sym = 16  # duration of one symbol in microseconds
    T_Slot = N_aUnitBackoffPeriod * T_Sym
    T_Byte = 2 * T_Sym
    T_PhyPre = 4 * T_Byte
    T_PhySFD = T_Byte
    T_MacHdr = MacHdrLen * T_Byte
    T_MacAck = T_PhyPre + T_PhySFD + MackAckLen * T_Byte
    T_SIFS = 12 * T_Sym
    T_LIFS = 40 * T_Sym
    T_Turnaround = 12 * T_Sym
    CW_MIN = 7
    CW_MAX = 255

    # variables
    n_MacPayloadBytes = 106  # num app data bytes
    n_Tx_ED = num_tx_nodes

    # calculated values
    t_EIFS = T_Turnaround + T_MacAck + (T_LIFS if n_MacPayloadBytes > N_aMaxSIFSFrameSize else T_SIFS)
    t_AppData = n_MacPayloadBytes * T_Byte
    t_Packet = T_PhyPre + T_PhySFD + T_MacHdr + t_AppData
    t_Collision = t_Packet + t_EIFS
    CW_f = n_Tx_ED * math.sqrt(2 * t_Collision / T_Slot)
    CW = round(CW_f)
    CW = int(CW)
    CW = max(CW, CW_MIN)
    CW = min(CW, CW_MAX)
    return CW


log = logging.getLogger('contiki_global_cp')


def default_callback(group, node, cmd, data):
    print("{} DEFAULT CALLBACK : Group: {}, NodeName: {}, Cmd: {}, Returns: {}".format(datetime.datetime.now(), group, node.name, cmd, data))


def print_response(group, node, data):
    print("{} Print response : Group:{}, NodeIP:{}, Result:{}".format(datetime.datetime.now(), group, node.ip, data))


def event_cb(mac_address, event_name, event_value):
    measurement_logger.log_measurement(event_name, event_value)
    # print("{} Node {} Event {}: {} ".format(datetime.datetime.now(), mac_address, event_name, event_value))


def main(args):
    contiki_nodes = global_node_manager.get_mac_address_list()
    print("Connected nodes", [str(node) for node in contiki_nodes])
    taisc_manager = TAISCMACManager(global_node_manager, "CSMA")
    app_manager = AppManager(global_node_manager)
    ret = taisc_manager.update_slotframe('./contiki_helpers/default_taisc_slotframe.csv')
    log.info(ret)
    ret = taisc_manager.update_macconfiguration({'IEEE802154e_macSlotframeSize': len(contiki_nodes)})
    log.info(ret)
    global_node_manager.start_local_monitoring_cp()
    gevent.sleep(5)
    app_manager.subscribe_events(["RIME_appPerPacket_rxstats"], event_cb, 0)
    gevent.sleep(5)

    while True:
        # activate receiver
        err1 = app_manager.update_configuration({"RIME_exampleUnicastActivateApplication": 1}, [1])
        log.info("Activate receiver: ERROR {}".format(err1))
        gevent.sleep(1)
        cw = cwold = calculateCWOpt(1)
        active_sender_address_list = []

        # add nodes
        for mac_address in contiki_nodes:
            if mac_address != 1:
                log.info("Adding sender {}!".format(mac_address))
                active_sender_address_list.append(mac_address)

                # update contention window
                cwold = cw
                cw = calculateCWOpt(len(active_sender_address_list))
                err1 = taisc_manager.update_macconfiguration({'IEEE802154_macCW': cw}, active_sender_address_list)
                log.info("Changed CW from {} to {}: ERROR {}!".format(cwold, cw, err1))

                # activate application on mac
                err1 = app_manager.update_configuration({"RIME_exampleUnicastActivateApplication": 1}, [mac_address])
                log.info("Activated application on {}: ERROR {}!".format(mac_address, err1))

                gevent.sleep(10)

        log.info("Switching all nodes to TDMA!")

        err1 = app_manager.update_configuration({"RIME_exampleUnicastActivateApplication": 0})
        log.info("Stopping APP: ERROR {}".format(err1))
        gevent.sleep(1)

        err1 = taisc_manager.activate_radio_program("TDMA")
        log.info("Activated TDMA: ERROR {}".format(err1))
        gevent.sleep(5)

        err1 = app_manager.update_configuration({"RIME_exampleUnicastActivateApplication": 1})
        log.info("Starting APP: ERROR {}".format(err1))

        log.info("Switching all nodes to TDMA dones!")
        gevent.sleep(30)

        err1 = app_manager.update_configuration({"RIME_exampleUnicastActivateApplication": 0})
        log.info("Stopping APP: ERROR {}".format(err1))
        gevent.sleep(1)

        err1 = taisc_manager.activate_radio_program("CSMA")
        log.info("Activated CSMA: ERROR {}".format(err1))
        gevent.sleep(5)


if __name__ == "__main__":
    try:
        from docopt import docopt
    except:
        print("""
        Please install docopt using:
            pip install docopt==0.6.1
        For more refer to:
        https://github.com/docopt/docopt
        """)
        raise

    args = docopt(__doc__, version=__version__)

    log_level = logging.INFO  # default
    if args['--verbose']:
        log_level = logging.DEBUG
    elif args['--quiet']:
        log_level = logging.ERROR

    logfile = None
    if args['--logfile']:
        logfile = args['--logfile']

    logging.basicConfig(filename=logfile, level=log_level,
                        format='%(asctime)s - %(name)s.%(funcName)s() - %(levelname)s - %(message)s')

    log.debug(args)

    config_file_path = args['--config']
    config = None
    with open(config_file_path, 'r') as f:
        config = yaml.load(f)
    global_node_manager = GlobalNodeManager(config)
    global_node_manager.set_default_callback(default_callback)

    nodes_file_path = args['--nodes']
    with open(nodes_file_path, 'r') as f:
        node_config = yaml.load(f)
    global_node_manager.wait_for_agents(node_config['ip_address_list'])

    measurements_file_path = args['--measurements']
    with open(measurements_file_path, 'r') as f:
        measurement_config = yaml.load(f)
    measurement_logger = MeasurementLogger.load_config(measurement_config)

    try:
        main(args)
    except KeyboardInterrupt:
        log.debug("Controller exits")
    finally:
        log.debug("Exit")
        measurement_logger.stop_logging()
        global_node_manager.stop()
