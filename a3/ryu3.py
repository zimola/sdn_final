from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ether_types
from ryu.lib.packet import arp,ipv4
from ryu.lib import hub
from ryu.lib import mac
import copy,itertools
from ryu.topology import event, switches
from ryu.topology.api import get_switch, get_link
import networkx as nx
from networkx.utils import pairwise
time_to_collect=10

class SimpleSwitch13(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch13, self).__init__(*args, **kwargs)
        self.net=nx.DiGraph()
        self.datapaths={}
        self.access_ports={}
        self.switches=[]
        self.switch_port_table={}
        self.interior_ports={}
        self.access_table={}
        self.all_pair_shortest_path={}


    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # install table-miss flow entry
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)
    @set_ev_cls(ofp_event.EventOFPStateChange,
                [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            if not datapath.id in self.datapaths:
                self.datapaths[datapath.id] = datapath
        elif ev.state == DEAD_DISPATCHER:
            if datapath.id in self.datapaths:
                del self.datapaths[datapath.id]
    def add_flow(self, dp, p, match, actions, idle_timeout=0, hard_timeout=0):
        ofproto = dp.ofproto
        parser = dp.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]

        mod = parser.OFPFlowMod(datapath=dp, priority=p,
                                idle_timeout=idle_timeout,
                                hard_timeout=hard_timeout,
                                match=match, instructions=inst)
        dp.send_msg(mod)
    def getall_pair_shortest_path(self):
        """
          this function computes two shortest path for each pair and adds them in a dictionary where key is the pair of nodes. 
          self.all_pair_shortest_path is similiar to {(2,3):[[2,4,3],[2,5,6,3]]}
        """
        edges=self.net.edges()
        edges=set(edges)
        edges=list(edges)
        nodes=self.net.nodes
        nodes=set(nodes)
        nodes=list(nodes)
        pairs=set(itertools.product(nodes, nodes))
        graph=copy.copy(self.net)
        total_edges=graph.edges()
        for pair in pairs:
            src,dst=pair
            try:
             edges_remain=[]
             path1=nx.shortest_path(graph,src,dst)
             edges_used=pairwise(path1)
             edges_remain=set(total_edges)-set(edges_used)
             if len(edges_remain)>0:
                newgraph=nx.DiGraph()
                newgraph.add_edges_from(edges_remain)
                path2=nx.shortest_path(newgraph,src,dst)
                self.all_pair_shortest_path[pair]=[path1,path2]
            except:
               pass
    def create_port_map(self, switch_list):
        for sw in switch_list:
            dpid = sw.dp.id
            self.switch_port_table.setdefault(dpid, set())
            self.interior_ports.setdefault(dpid, set())
            self.access_ports.setdefault(dpid, set())

            for p in sw.ports:
                self.switch_port_table[dpid].add(p.port_no)
    def get_host_location(self, host_ip):
        for key in self.access_table.keys():
            if self.access_table[key][0] == host_ip:
                return key
        self.logger.info("%s ip to dpid not found." % host_ip)
        return None
    def create_access_ports(self):
        for sw in self.switch_port_table:
            all_port_table = self.switch_port_table[sw]
            interior_port = self.interior_ports[sw]
            self.access_ports[sw] = all_port_table - interior_port
             
    events = [event.EventSwitchEnter,
              event.EventSwitchLeave, event.EventPortAdd,
              event.EventPortDelete, event.EventPortModify,
              event.EventLinkAdd, event.EventLinkDelete]
    
    @set_ev_cls(events)
    def get_topology(self, ev):
        switch_list = copy.copy(get_switch(self, None)) 
        self.create_port_map(switch_list) 
        self.switches = self.switch_port_table.keys()        
        links = copy.copy(get_link(self, None))
        edges_list=[]  # extra list item for constructing nx graph
        if len(links)>0:
            for link in links:
                src = link.src
                dst = link.dst
                edges_list.append((src.dpid,dst.dpid,{'port':link.src.port_no})) 
                if link.src.dpid in self.switches:
                    self.interior_ports[link.src.dpid].add(link.src.port_no)
                if link.dst.dpid in self.switches:
                    self.interior_ports[link.dst.dpid].add(link.dst.port_no)
            self.create_access_ports()    
            self.net.add_weighted_edges_from(edges_list)  
            self.getall_pair_shortest_path()    
 
    def get_port(self, dst_ip, access_table):
        if access_table:
            if isinstance(access_table.values()[0], tuple):
                for key in access_table.keys():
                    if dst_ip == access_table[key][0]:
                        dst_port = key[1]
                        return dst_port
        return None
    def register_access_info(self, dpid, in_port, ip, mac):
        if in_port in self.access_ports[dpid]:
            if (dpid, in_port) in self.access_table:
                if self.access_table[(dpid, in_port)] == (ip, mac):
                    return
                else:
                    self.access_table[(dpid, in_port)] = (ip, mac)
                    return
            else:
                self.access_table.setdefault((dpid, in_port), None)
                self.access_table[(dpid, in_port)] = (ip, mac)
                return                       

    def flood(self, msg):
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        for dpid in self.access_ports:
            for port in self.access_ports[dpid]:
                if (dpid, port) not in self.access_table.keys():
                    datapath = self.datapaths[dpid]
                    out = self._build_packet_out(
                        datapath, ofproto.OFP_NO_BUFFER,
                        ofproto.OFPP_CONTROLLER, port, msg.data)
                    datapath.send_msg(out)
        
    def arp_forwarding(self, msg, src_ip, dst_ip):
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        result = self.get_host_location(dst_ip)
        if result: 
            datapath_dst, out_port = result[0], result[1]
            datapath = self.datapaths[datapath_dst]
            out = self._build_packet_out(datapath, ofproto.OFP_NO_BUFFER,
                                         ofproto.OFPP_CONTROLLER,
                                         out_port, msg.data)
            datapath.send_msg(out)
        else:
            self.flood(msg)
    def get_sw(self, dpid, in_port, src, dst):
        src_sw = dpid
        dst_sw = None

        src_location = self.get_host_location(src)
        if in_port in self.access_ports[dpid]:
            if (dpid,  in_port) == src_location:
                src_sw = src_location[0]
            else:
                return None

        dst_location = self.get_host_location(dst)
        if dst_location:
            dst_sw = dst_location[0]

        return src_sw, dst_sw
    def get_group_id(self,dst_ip):
        """
         construct group id from dest_ip
        """
        return int(dst_ip.split('.')[3])-1
    def build_flow(self, msg,priority, flow_info, src_port, out_port, out_port2):
        datapath = msg.datapath
        parser = datapath.ofproto_parser
        actions = [parser.OFPActionDecNwTtl()]
        if out_port2: # if no out_port 2 is supplied meaning that its not group entry
            group_id = self.get_group_id(flow_info[2])
            self.send_group_mod(datapath,group_id,out_port,out_port,out_port2,out_port2)
            actions.append(parser.OFPActionGroup(group_id))
        else:
            actions.append(parser.OFPActionOutput(out_port))
        
        match = parser.OFPMatch(in_port=src_port, eth_type=flow_info[0],ipv4_src=flow_info[1], ipv4_dst=flow_info[2])
        self.add_flow(datapath, priority, match, actions,idle_timeout=60,hard_timeout=60)
        
        out = datapath.ofproto_parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id, data=msg.data, in_port=src_port, actions=actions)
        datapath.send_msg(out)
        
    def shortest_forwarding(self, msg, eth_type, ip_src, ip_dst):
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']
        flow_info = (eth_type, ip_src, ip_dst, in_port)
        back_info = (flow_info[0], flow_info[2], flow_info[1])
        result = self.get_sw(datapath.id, in_port, ip_src, ip_dst)
        if result:
           src_sw, dst_sw = result[0], result[1]
           if src_sw != dst_sw:
              if dst_sw:               
                
                path,backup_path=self.all_pair_shortest_path[(src_sw,dst_sw)]
                print(path, backup_path)
                sw_pos_in_path=path.index(datapath.id)
                sw_pos_in_backuppath=backup_path.index(datapath.id)
                if sw_pos_in_path+1 != len(path):
                    nextsw=path[sw_pos_in_path+1]
                    edge_attrib=nx.get_edge_attributes(self.net,'weight')
                    port=edge_attrib[(datapath.id,nextsw)]['port'] # find port in first path
                if sw_pos_in_backuppath+1 != len(backup_path):
                    nextsw=backup_path[sw_pos_in_backuppath+1]
                    edge_attrib=nx.get_edge_attributes(self.net,'weight')
                    port2=edge_attrib[(datapath.id,nextsw)]['port']# find port in second path
                self.build_flow(msg, 1, flow_info, in_port, port, port2)
     

           else:
                out_port = self.get_port(flow_info[2], self.access_table)
                if out_port is None:
                    return
                self.build_flow(msg, 1, flow_info, in_port, out_port, False)         
               
        return

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        """
        """
        msg = ev.msg
        datapath = msg.datapath
        in_port = msg.match['in_port']
        pkt = packet.Packet(msg.data)
        arp_pkt = pkt.get_protocol(arp.arp)
        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        if isinstance(arp_pkt, arp.arp):
            self.register_access_info(datapath.id, in_port, arp_pkt.src_ip, arp_pkt.src_mac)
            self.arp_forwarding(msg, arp_pkt.src_ip, arp_pkt.dst_ip)

        if isinstance(ip_pkt, ipv4.ipv4):
            if ip_pkt.src == '0.0.0.0':
                return 
            if len(pkt.get_protocols(ethernet.ethernet)):
                eth_type = pkt.get_protocols(ethernet.ethernet)[0].ethertype
                
                self.shortest_forwarding(msg, eth_type, ip_pkt.src, ip_pkt.dst)
                
    
    def _build_packet_out(self, datapath, buffer_id, src_port, dst_port, data):
        actions = []
        if dst_port:
            actions.append(datapath.ofproto_parser.OFPActionOutput(dst_port))

        msg_data = None
        if buffer_id == datapath.ofproto.OFP_NO_BUFFER:
            if data is None:
                return None
            msg_data = data

        out = datapath.ofproto_parser.OFPPacketOut(
            datapath=datapath, buffer_id=buffer_id,
            data=msg_data, in_port=src_port, actions=actions)
        return out
    def send_group_mod(self,datapath,group_id,watch_port1,out_port1,watch_port2,out_port2):
        ofp = datapath.ofproto
        ofp_parser = datapath.ofproto_parser
        actions1 = [ofp_parser.OFPActionOutput(out_port1)]
        actions2 = [ofp_parser.OFPActionOutput(out_port2)]
        weight = 0
        buckets = [ofp_parser.OFPBucket(weight,watch_port1,ofp.OFPG_ANY,actions1),ofp_parser.OFPBucket(weight,watch_port2,ofp.OFPG_ANY,actions2)]
        req = ofp_parser.OFPGroupMod(datapath,ofp.OFPGC_ADD,ofp.OFPGT_FF,group_id,buckets)
        datapath.send_msg(req)
    def send_packet_out(self, datapath, buffer_id, src_port, dst_port, data):
        out = self._build_packet_out(datapath, buffer_id,
                                     src_port, dst_port, data)
        if out:
            datapath.send_msg(out)
 
