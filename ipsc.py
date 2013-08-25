# Copyright (c) 2013 Cortney T. Buffington, N0MJS n0mjs@me.com
#
# This work is licensed under the Creative Commons Attribution-ShareAlike
# 3.0 Unported License.To view a copy of this license, visit
# http://creativecommons.org/licenses/by-sa/3.0/ or send a letter to
# Creative Commons, 444 Castro Street, Suite 900, Mountain View,
# California, 94041, USA.

from __future__ import print_function
from twisted.internet.protocol import DatagramProtocol
from twisted.internet import reactor
from twisted.internet import task
import sys
import argparse
import binascii
import hmac
import hashlib
import socket

#from logging.config import dictConfig
#import logging


#************************************************
#     IMPORTING OTHER FILES - '#include'
#************************************************

# Import system logger configuration
#
try:
    from ipsc_logger import logger
except ImportError:
    sys.exit('System logger configuraiton not found or invalid')

# Import configuration and informational data structures
#
try:
    from my_ipsc_config import NETWORK
except ImportError:
    sys.exit('Configuration file not found, or not valid formatting')

# Import IPSC message types and version information
#
try:
    from ipsc_message_types import *
except ImportError:
    sys.exit('IPSC message types file not found or invalid')

# Import IPSC flag mask values
#
try:
    from ipsc_mask import *
except ImportError:
    sys.exit('IPSC mask values file not found or invalid')
   


#************************************************
#     GLOBALLY SCOPED FUNCTIONS
#************************************************


# Remove the hash from a paket and return the payload
#
def strip_hash(_data):
    return _data[:-10]


# Determine if the provided peer ID is valid for the provided network 
#
def valid_peer(_peer_list, _peerid):
    if _peerid in _peer_list:
        return True
    return False


# Determine if the provided master ID is valid for the provided network
#
def valid_master(_network, _peerid):
    if NETWORK[_network]['MASTER']['RADIO_ID'] == _peerid:
        return True
    else:
        return False


# Take a packet to be SENT, calcualte auth hash and return the whole thing
#
def hashed_packet(_key, _data):
    hash = binascii.a2b_hex((hmac.new(_key,_data,hashlib.sha1)).hexdigest()[:20])
    return (_data + hash)    
    
    
# Take a RECEIVED packet, calculate the auth hash and verify authenticity
#
def validate_auth(_key, _data):
    _log = logger.debug
    _payload = _data[:-10]
    _hash = _data[-10:]
    _chk_hash = binascii.a2b_hex((hmac.new(_key,_payload,hashlib.sha1)).hexdigest()[:20])
    
    if _chk_hash == _hash:
        _log('    AUTH: Valid   - Payload: %s, Hash: %s', binascii.b2a_hex(_payload), binascii.b2a_hex(_hash))
        return True
    else:
        _log('    AUTH: Invalid - Payload: %s, Hash: %s', binascii.b2a_hex(_payload), binascii.b2a_hex(_hash))
        return False

# Forward Group Voice Packet
# THIS IS BROKEN - BEGIN WORK HERE. REPLACING SEGMENTS ISN'T REFERENCING THE RIGHT SUBSTITUTE DATA AND 
# I'M GOIGN TO BED NOW.
def fwd_group_voice(_network, _data):
    _src_group = _data[9:12]
    _src_ipsc  = _data[1:5]
    
    for source in NETWORK[_network]['RULES']['GROUP_VOICE']:
        if source['SRC_GROUP'] == _src_group:
            print(binascii.b2a_hex(_data))
            _data = _data.replace(_src_ipsc, NETWORK[(source['DST_NET'])]['LOCAL']['RADIO_ID'])
            _data = _data.replace(_src_group, source['DST_GROUP'])
            _data = hashed_packet(NETWORK[(source['DST_NET'])]['LOCAL']['AUTH_KEY'], _data)
            print(binascii.b2a_hex(_data))
            print()
    # Send packet

# Take a recieved peer list and the network it belongs to, process and populate the
# data structure in my_ipsc_config with the results.
#
def process_peer_list(_data, _network, _peer_list):
    _log = logger.debug
    
    NETWORK[_network]['MASTER']['STATUS']['PEER-LIST'] = True
    _num_peers = int(str(int(binascii.b2a_hex(_data[5:7]), 16))[1:])
    NETWORK[_network]['LOCAL']['NUM_PEERS'] = _num_peers
    
    _log('<<- (%s) The Peer List has been Received from Master\n%s \
    There are %s peers in this IPSC Network', _network, (' '*(len(_network)+7)), _num_peers)
    
    for i in range(7, (_num_peers*11)+7, 11):
        hex_radio_id = (_data[i:i+4])
        hex_address  = (_data[i+4:i+8])
        hex_port     = (_data[i+8:i+10])
        hex_mode     = (_data[i+10:i+11])
        decoded_mode = mode_decode(hex_mode, _data)

        if hex_radio_id not in _peer_list:
            _peer_list.append(hex_radio_id)
            NETWORK[_network]['PEERS'].append({
                'RADIO_ID':  hex_radio_id, 
                'IP':        socket.inet_ntoa(hex_address), 
                'PORT':      int(binascii.b2a_hex(hex_port), 16), 
                'MODE':      hex_mode,
                'PEER_OPER': decoded_mode[0],
                'PEER_MODE': decoded_mode[1],
                'TS1_LINK':  decoded_mode[2],
                'TS2_LINK':  decoded_mode[3],
                'STATUS':    {'CONNECTED': False, 'KEEP_ALIVES_SENT': 0, 'KEEP_ALIVES_MISSED': 0, 'KEEP_ALIVES_OUTSTANDING': 0}
            })       
    return _peer_list


# Given a mode byte, decode the functions and return a tuple of results
#
def mode_decode(_mode, _data):
    _log = logger.debug
    _mode = int(binascii.b2a_hex(_mode), 16)
    link_op   = _mode & PEER_OP_MSK
    link_mode = _mode & PEER_MODE_MSK
    ts1       = _mode & IPSC_TS1_MSK
    ts2       = _mode & IPSC_TS2_MSK    
    # Determine whether or not the peer is operational
    if   link_op == 0b01000000:
        _peer_op = True
    elif link_op == 0b00000000:
        _peer_op = False
    else:
        _peer_op = False  
    # Determine the operational mode of the peer
    if   link_mode == 0b00000000:
        _peer_mode = 'NO_RADIO'
    elif link_mode == 0b00010000:
        _peer_mode = 'ANALOG'
    elif link_mode == 0b00100000:
        _peer_mode = 'DIGITAL'
    else:
        _peer_node = 'NO_RADIO'
    # Determine whether or not timeslot 1 is linked
    if ts1 == 0b00001000:
         _ts1 = True
    else:
         _ts1 = False
    # Determine whether or not timeslot 2 is linked
    if ts2 == 0b00000010:
        _ts2 = True
    else:
        _ts2 = False  
     # Return a tuple with the decoded values   
    return _peer_op, _peer_mode, _ts1, _ts2


# Gratuituous print-out of the peer list.. Pretty much debug stuff.
#
def print_peer_list(_network):
    _log = logger.info
#    os.system('clear')
    if not NETWORK[_network]['PEERS']:
        print('No peer list for: {}' .format(_network))
        return
    
    print('Peer List for: %s' % _network)
    for dictionary in NETWORK[_network]['PEERS']:
        if dictionary['RADIO_ID'] == NETWORK[_network]['LOCAL']['RADIO_ID']:
            me = '(self)'
        else:
            me = ''
        print('\tRADIO ID: {} {}' .format(int(binascii.b2a_hex(dictionary['RADIO_ID']), 16), me))
        print('\t\tIP Address: {}:{}' .format(dictionary['IP'], dictionary['PORT']))
        print('\t\tOperational: {},  Mode: {},  TS1 Link: {},  TS2 Link: {}' .format(dictionary['PEER_OPER'], dictionary['PEER_MODE'], dictionary['TS1_LINK'], dictionary['TS2_LINK']))
        print('\t\tStatus: {},  KeepAlives Sent: {},  KeepAlives Outstanding: {},  KeepAlives Missed: {}' .format(dictionary['STATUS']['CONNECTED'], dictionary['STATUS']['KEEP_ALIVES_SENT'], dictionary['STATUS']['KEEP_ALIVES_OUTSTANDING'], dictionary['STATUS']['KEEP_ALIVES_MISSED']))
    print('')
        


#************************************************
#********                             ***********
#********    IPSC Network 'Engine'    ***********
#********                             ***********
#************************************************

#************************************************
#     INITIAL SETUP of IPSC INSTANCE
#************************************************

class IPSC(DatagramProtocol):
    
    # Modify the initializer to set up our environment and build the packets
    # we need to maitain connections
    #
    def __init__(self, *args, **kwargs):
        if len(args) == 1:
            # Housekeeping: create references to the configuration and status data for this IPSC instance.
            # Some configuration objects that are used frequently and have lengthy names are shortened
            # such as (self._master_sock) expands to (self._config['MASTER']['IP'], self._config['MASTER']['PORT'])
            #
            self._network = args[0]
            self._config = NETWORK[self._network]
            #
            self._local = self._config['LOCAL']
            self._local_stat = self._local['STATUS']
            self._local_id = self._local['RADIO_ID']
            #
            self._master = self._config['MASTER']
            self._master_stat = self._master['STATUS']
            self._master_sock = self._master['IP'], self._master['PORT']
            #
            self._peers = self._config['PEERS']
            #
            # This is a regular list to store peers for the IPSC. At times, parsing a simple list is much less
            # Spendy than iterating a list of dictionaries... Maybe I'll find a better way in the future. Also
            # We have to know when we have a new peer list, so a variable to indicate we do (or don't)
            #
            self._peer_list = []
            self._peer_list_new = False
            
            args = ()
            
            # Packet 'constructors' - builds the necessary control packets for this IPSC instance
            #
            self.TS_FLAGS             = (self._local['MODE'] + self._local['FLAGS'])
            self.MASTER_REG_REQ_PKT   = (MASTER_REG_REQ + self._local_id + self.TS_FLAGS + IPSC_VER)
            self.MASTER_ALIVE_PKT     = (MASTER_ALIVE_REQ + self._local_id + self.TS_FLAGS + IPSC_VER)
            self.PEER_LIST_REQ_PKT    = (PEER_LIST_REQ + self._local_id)
            self.PEER_REG_REQ_PKT     = (PEER_REG_REQ + self._local_id + IPSC_VER)
            self.PEER_REG_REPLY_PKT   = (PEER_REG_REPLY + self._local_id + IPSC_VER)
            self.PEER_ALIVE_REQ_PKT   = (PEER_ALIVE_REQ + self._local_id + self.TS_FLAGS)
            self.PEER_ALIVE_REPLY_PKT = (PEER_ALIVE_REPLY + self._local_id + self.TS_FLAGS)
                  
        else:
            # If we didn't get called correctly, log it!
            #
            logger.error('(%s) Unexpected arguments found.', self._network)
            
    # This is called by REACTOR when it starts, We use it to set up the timed
    # loop for each instance of the IPSC engine
    #       
    def startProtocol(self):
        # Timed loop for IPSC connection establishment and maintenance
        # Others could be added later for things like updating a Web
        # page, etc....
        #
        self._call = task.LoopingCall(self.timed_loop)
        self._loop = self._call.start(self._local['ALIVE_TIMER'])


#************************************************
#     FUNCTIONS FOR IPSC Network Engine
#************************************************

#************************************************
#     TIMED LOOP - MY CONNECTION MAINTENANCE
#************************************************

    def timed_loop(self):    
        print_peer_list(self._network)

        if (self._master_stat['CONNECTED'] == False):
            reg_packet = hashed_packet(self._local['AUTH_KEY'], self.MASTER_REG_REQ_PKT)
            self.transport.write(reg_packet, (self._master_sock))
            logger.debug('->> (%s) Master Registration Request To:%s From:%s', self._network, self._master_sock, binascii.b2a_hex(self._local_id))
        
        elif (self._master_stat['CONNECTED'] == True):
            master_alive_packet = hashed_packet(self._local['AUTH_KEY'], self.MASTER_ALIVE_PKT)
            self.transport.write(master_alive_packet, (self._master_sock))
            logger.debug('->> (%s) Master Keep-alive %s Sent To:%s', self._network, self._master_stat['KEEP_ALIVES_SENT'], self._master_sock)
            
            if (self._master_stat['KEEP_ALIVES_OUTSTANDING']) > 0:
                self._master_stat['KEEP_ALIVES_MISSED'] += 1
            
            if self._master_stat['KEEP_ALIVES_OUTSTANDING'] >= self._local['MAX_MISSED']:
                self._master_stat['CONNECTED'] = False
                logger.error('Maximum Master Keep-Alives Missed -- De-registering the Master')
                
            self._master_stat['KEEP_ALIVES_SENT'] += 1
            self._master_stat['KEEP_ALIVES_OUTSTANDING'] += 1
            
        else:
            logger.error('->> (%s) Master in UNKOWN STATE:%s:%s', self._network, self._master_sock)
                
        if  ((self._master_stat['CONNECTED'] == True) and (self._master_stat['PEER-LIST'] == False)):     
            peer_list_req_packet = hashed_packet(self._local['AUTH_KEY'], self.PEER_LIST_REQ_PKT)
            self.transport.write(peer_list_req_packet, (self._master_sock))
            logger.debug('->> (%s) List Reqested from Master:%s', self._network, self._master_sock)

        if (self._master_stat['PEER-LIST'] == True):
            for peer in (self._peers):
                if (peer['RADIO_ID'] == self._local_id): # We are in the peer-list, but don't need to talk to ourselves
                    continue
                if peer['STATUS']['CONNECTED'] == False:
                    peer_reg_packet = hashed_packet(self._local['AUTH_KEY'], self.PEER_REG_REQ_PKT)
                    self.transport.write(peer_reg_packet, (peer['IP'], peer['PORT']))
                    logger.debug('->> (%s) Peer Registration Request To:%s:%s From:%s', self._network, peer['IP'], peer['PORT'], binascii.b2a_hex(self._local_id))
                elif peer['STATUS']['CONNECTED'] == True:
                    peer_alive_req_packet = hashed_packet(self._local['AUTH_KEY'], self.PEER_ALIVE_REQ_PKT)
                    self.transport.write(peer_alive_req_packet, (peer['IP'], peer['PORT']))
                    logger.debug('->> (%s) Peer Keep-Alive Request To:%s:%s From:%s', self._network, peer['IP'], peer['PORT'], binascii.b2a_hex(self._local_id))

                    if peer['STATUS']['KEEP_ALIVES_OUTSTANDING'] > 0:
                        peer['STATUS']['KEEP_ALIVES_MISSED'] += 1
            
                    if peer['STATUS']['KEEP_ALIVES_OUTSTANDING'] >= self._local['MAX_MISSED']:
                        peer['STATUS']['CONNECTED'] = False
                        self._peer_list.remove(peer['RADIO_ID']) # Remove the peer from the simple list FIRST
                        self._peers.remove(peer)                 # Becuase once it's out of the dictionary, you can't use it for anything else.
                        logger.error('Maximum Peer Keep-Alives Missed -- De-registering the Peer: %s', peer)
                    
                    peer['STATUS']['KEEP_ALIVES_SENT'] += 1
                    peer['STATUS']['KEEP_ALIVES_OUTSTANDING'] += 1
        
        logger.debug('(%s) timed loop finished', self._network) # temporary debugging to make sure this part runs
    
    
    
#************************************************
#     RECEIVED DATAGRAM - ACT IMMEDIATELY!!!
#************************************************

    # Actions for recieved packets by type: Call a function or process here...
    #
    def datagramReceived(self, data, (host, port)):
        logger.debug('received %r from %s:%d', binascii.b2a_hex(data), host, port)

        _packettype = data[0:1]
        _peerid     = data[1:5]
        _dec_peerid = int(binascii.b2a_hex(_peerid), 16)
        
        # First action: if Authentication is active, authenticate the packet
        #
        if bool(self._local['AUTH_KEY']) == True:
            if validate_auth(self._local['AUTH_KEY'], data) == False:
                logger.warning('(%s) AuthError: IPSC packet failed authentication. Type %s: Peer ID: %s', self._network, binascii.b2a_hex(_packettype), _dec_peerid)
                return
            data = strip_hash(data)

        # Packets generated by "users" that are the most common should come first for efficiency.
        #
        if (_packettype == GROUP_VOICE):
            if not(valid_master(self._network, _peerid) == False or valid_peer(self._peer_list, _peerid) == False):
                logger.warning('(%s) PeerError: Peer not in peer-list: %s', self._network, _dec_peerid)
                return
            fwd_group_voice(self._network, data)
            
            logger.debug('<<- (%s) Group Voice Packet From:%s:%s', self._network, host, port)

        # IPSC keep alives, master and peer, come next in processing priority
        #
        elif (_packettype == PEER_ALIVE_REQ):
            if valid_peer(self._peer_list, _peerid) == False:
                
                logger.warning('(%s) PeerError: Peer %s not in peer-list: %s', self._network, _dec_peerid, self._peer_list)
                return
        
            logger.debug('<<- (%s) Peer Keep-alive Request From Peer ID %s at:%s:%s', self._network, _dec_peerid, host, port)
            peer_alive_reply_packet = hashed_packet(self._local['AUTH_KEY'], self.PEER_ALIVE_REPLY_PKT)
            self.transport.write(peer_alive_reply_packet, (host, port))
            logger.debug('->> (%s) Peer Keep-alive Reply sent To:%s:%s', self._network, host, port)

        elif (_packettype == MASTER_ALIVE_REPLY):
            if valid_master(self._network, _peerid) == False:
                logger.warning('(%s) PeerError: Peer %s not in peer-list: %s', self._network, _dec_peerid, self._peer_list)
                return
                
            logger.debug('<<- (%s) Master Keep-alive Reply From: %s \t@ IP: %s:%s', self._network, _dec_peerid, host, port)
            self._master_stat['KEEP_ALIVES_OUTSTANDING'] = 0

        elif (_packettype == PEER_ALIVE_REPLY):
            logger.debug('<<- (%s) Peer Keep-alive Reply From:   %s \t@ IP: %s:%s', self._network, _dec_peerid, host, port)
            for peer in self._config['PEERS']:
                if peer['RADIO_ID'] == _peerid:
                    peer['STATUS']['KEEP_ALIVES_OUTSTANDING'] = 0     
        
        # Registration requests and replies are infrequent, but important. Peer lists can go here too as a part
        # of the registration process.
        #    
        elif (_packettype == MASTER_REG_REQ):
            logger.debug('<<- (%s) Master Registration Packet Recieved', self._network)

        elif (_packettype == MASTER_REG_REPLY):
            self._master['RADIO_ID'] = _peerid
            self._master_stat['CONNECTED'] = True
            self._master_stat['KEEP_ALIVES_OUTSTANDING'] = 0
            logger.debug('<<- (%s) Master Registration Reply From:%s:%s ', self._network, host, port)

        elif (_packettype == PEER_REG_REQ):
            logger.debug('<<- (%s) Peer Registration Request From Peer ID %s at:%s:%s', self._network, _dec_peerid, host, port)
            peer_reg_reply_packet = hashed_packet(self._local['AUTH_KEY'], self.PEER_REG_REPLY_PKT)
            self.transport.write(peer_reg_reply_packet, (host, port))
            logger.debug('->> (%s) Peer Registration Reply Sent To:%s:%s', self._network, host, port)

        elif (_packettype == PEER_REG_REPLY):
            logger.debug('<<- (%s) Peer Registration Reply From: %s \t@ IP: %s:%s', self._network, _dec_peerid, host, port)
            for peer in self._config['PEERS']:
                if peer['RADIO_ID'] == _peerid:
                    peer['STATUS']['CONNECTED'] = True

        elif (_packettype == PEER_LIST_REPLY):
            logger.debug('<<- (%s) Peer List Received From:%s:%s', self._network, host, port)
            self._peer_list = process_peer_list(data, self._network, self._peer_list)

        # Other "user" related packet types that we don't do much or anything with yet
        #
        elif (_packettype == PVT_VOICE):
            logger.debug('<<- (%s) Voice Packet From:%s:%s', self._network, host, port)
            
        elif (_packettype == GROUP_DATA):
            logger.debug('<<- (%s) Group Data Packet From:%s:%s', self._network, host, port)
            
        elif (_packettype == PVT_DATA):
            logger.debug('<<- (%s) Private Data Packet From From:%s:%s', self._network, host, port)
            
        elif (_packettype == DE_REG_REQ):
            logger.debug('<<- (%s) Peer De-Registration Request From:%s:%s', self._network, host, port)
            
        elif (_packettype == DE_REG_REPLY):
            logger.debug('<<- (%s) Peer De-Registration Reply From:%s:%s', self._network, host, port)
            
        elif (_packettype == RPT_WAKE_UP):
            logger.debug('<<- (%s) Repeater Wake-Up Packet From:%s:%s', self._network, host, port)
    
        # Technically, we're not paying any attention to these types because we're not part of the XCMP call control structure
        #
        elif (_packettype == XCMP_XNL):
            logger.debug('<<- (%s) XCMP_XNL From:%s:%s, but we did not indicate XCMP capable!', self._network, host, port)
            
        elif (_packettype in (CALL_CTL_1, CALL_CTL_2, CALL_CTL_3)):
            logger.debug('<<- (%s) Call Control Packet From:%s:%s', self._network, host, port)
            
        # If there's a packet type we don't know aobut, it should be logged so we can figure it out and take an appropriate action!    
        else:
            packet_type = binascii.b2a_hex(_packettype)
            logger.error('<<- (%s) Received Unprocessed Type %s From:%s:%s', self._network, packet_type, host, port)



#************************************************
#      MAIN PROGRAM LOOP STARTS HERE
#************************************************

if __name__ == '__main__':
    networks = {}
    for ipsc_network in NETWORK:
        networks[ipsc_network] = IPSC(ipsc_network)
        if (NETWORK[ipsc_network]['LOCAL']['ENABLED']):            
            reactor.listenUDP(NETWORK[ipsc_network]['LOCAL']['PORT'], networks[ipsc_network])
    reactor.run()