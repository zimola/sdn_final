import networkx as nx
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import CPULimitedHost
from mininet.link import TCLink
from mininet.node import Controller, RemoteController
from mininet.cli import CLI
from mininet.log import setLogLevel
import re,random,time
from networkx.utils import pairwise

class CompleteGraphTopo(Topo):
    def build(self):
        graph=nx.DiGraph()
        edges=[(0, 1), (1, 0), (0, 2), (2, 0), (0, 3), (3, 0), (1, 2), (2, 1), (1, 5), (5, 1), (1, 8), (8, 1), (2, 3), (3,2), (2, 6), (6, 2), (2, 4), (4, 2), (3, 6), (6, 3), (4, 5), (5, 4), (4, 7), (7, 4), (4, 8), (8, 4), (5, 6), (6, 5),(5, 7), (7, 5), (5, 9), (9, 5), (6, 7), (7, 6), (9, 6), (6, 9), (8, 9), (9, 8)]
        for (x,y) in edges:
            if (y,x) in edges:
                edges.remove((y,x))
        graph.add_edges_from(edges)
        total_node=len(graph.nodes)
        for node in range(total_node):
            switch = self.addSwitch('s%s'%(node+1))
            host = self.addHost('h%s'%(node+1),cpu=.5/total_node)
            self.addLink( host, switch)
        for (sw1, sw2) in edges:
            sw1=int(sw1)+1
            sw2=int(sw2)+1
            self.addLink("s%d" % sw1, "s%d" % sw2)
 
def ping(net,nodes,size='',count='',rate='',timeout=''):
          """
          """
          if rate!='':
           rate=' -i '+str(rate)
          if timeout!='':
             timeout=' -w '+str(timeout)
          if size !='':
             size='-s '+str(size)
          if count !='':
             count=' -c '+str(count)
          src,dest=nodes
          pingstats=src.cmd( 'ping %s %s' % (size+count+rate+timeout, dest.IP()) )
          pingstats= pingstats.split('\r\n')
          
          try:
            sent,received,loss,time=re.findall('\d+', pingstats[-3])
          
            min_,avg,max_,mdev=pingstats[-2].split('=')[1].strip().split(' ')[0].split('/') 
          except:
           return 1,0,64,64 # 64 is the ttl
           #import pdb;pdb.set_trace() # 100% packet loss
          return sent,received,min_,avg 
def get_path_length(net,src,dst):
    result=src.cmd('traceroute -n %s'%dst.IP())
    try:
      return int(result.split('\r\n')[-2].strip()[0])-1
    except:
       return 'Can not find path length'
def getNum(string):
          return float(re.findall('\d+.\d+',string)[0])       
def doIperf(net,src,dst,port=5001,startLoad=10,time=5,datasize=1): # 10*96bytes per secodn
          dst.cmd('sudo pkill iperf')          
          dst.cmd(('iperf -s -p%s -u -D')%(port))
          output=src.cmd(('iperf  -c %s  -p %s -u -t %d -b %sM')%(dst.IP(),port,time,datasize)) 
          time=0.0
          datasize_tx=0.0
          bitrate=0.0          
          try:
             #import pdb;pdb.set_trace()
             print 'iperf running for load '+str(datasize)
             output=output.split('\r\n')[-4].split('-')[1].split('  ')
             time=getNum(output[0])
             datasize_tx=getNum(output[1])
             bitrate=getNum(output[2])
          except:
                return [time,datasize_tx,bitrate]
          return [time,datasize_tx,bitrate]
def getavg(lst):
   return sum(lst)/len(lst)
   
def enable_BFD(net):
    """
     Bidirectional Forwarding Detection(BFD) is a network protocol used to detect link failure between two forwarding elements. 
    """
    switches=net.switches
    for switch in switches:
        ofp_version(switch, ['OpenFlow13'])
        intfs=switch.nameToIntf.keys()[1:]
        for intf in intfs:
            switch.cmd('ovs-vsctl set interface "%s" bfd:enable=true'%intf)
            
def ofp_version(switch, protocols):
    """
     sets openFlow version for each switch from mininet.
    """
    protocols_str = ','.join(protocols)
    command = 'ovs-vsctl set Bridge %s protocols=%s' % (switch, protocols)
    switch.cmd(command.split(' '))
def sw_link_map(net):
    """
     constructs a links map where keys are switches and values are link object 
     for links between switches
    """
    links_obj=net.links
    link_objs_filtered={}
    for obj in links_obj:
        if obj.intf1.name.find('h')<1 or obj.intf2.name.find('h')<1: 
           continue
        intf1=int(obj.intf1.name.split('-')[0].replace('s',''))
        intf2=int(obj.intf2.name.split('-')[0].replace('s',''))
        link_objs_filtered[(intf1,intf2)]=obj
    return link_objs_filtered
def bi_direct_edges(edges):
    bidirectEdges=[]
    for item in edges:
        bidirectEdges.append(item)
        bidirectEdges.append((item[1],item[0])) 
    return bidirectEdges  
def runner():
    "Create and run a custom topo with adjustable link parameters"
    topo = CompleteGraphTopo( )
    c = RemoteController('c', '127.0.0.1', 6633)
    net = Mininet( topo=topo,
                   controller=None,
                              host=CPULimitedHost, link=TCLink ,waitConnected=True,autoSetMacs=True)

    net.addController(c)           
    net.start()
    enable_BFD(net)# enable bfd
    link_fail_dict=sw_link_map(net)
    edges=link_fail_dict.keys() # keys of link_fail_dict has all the edges of the graph
    edges=bi_direct_edges(edges) # make edges bi directional so that nx can find path
    graph=nx.DiGraph()
    graph.add_edges_from(edges) # construct graph from edges obtained from mininet net obj
    random.seed(30) # set seed for random number
    test_pair=[(0,7),(3,8),(0,9),(8,6),(9,1)] 
    result={'hop':[],'delay':[],'throughput':[]}
    time.sleep(8)
    for pair in test_pair:
        host1,host2=pair
        src=net.getNodeByName('h'+str(host1+1))
        dst=net.getNodeByName('h'+str(host2+1))
        path=nx.shortest_path(graph,host1+1,host2+1) # compute shortest path from graph
        links_between_pair=pairwise(path) # make links from path
        randindex=random.randint(0,len(links_between_pair)-1) # find random index  to be used to get failed link
        link_to_fail=links_between_pair[randindex] # get random link to be failed using random index
        print 'Failing link between',link_to_fail
        
        if link_fail_dict.has_key(link_to_fail):
           link_to_fail_obj=link_fail_dict[link_to_fail] # find the link obj to fail
        elif link_fail_dict.has_key(link_to_fail[::-1]): # link might be with reverse key
             link_to_fail_obj=link_fail_dict[link_to_fail[::-1]] # find the link obj to fail 
             link_to_fail= link_to_fail[::-1]  
        try:
           print ping(net,[src,dst],64,2)# send some packets before calculation
           net.delLink(link_to_fail_obj) # delete link to fail it
        except:
          import pdb;pdb.set_trace()
        time.sleep(5)        
        sent,received,min_,avg=ping(net,[src,dst],1024,5)
        print 'Delay ',avg,' for ',pair
        result['delay'].append(float(avg))
        hop=get_path_length(net,src,dst)
        print 'Hop ',hop,' for ',pair
        result['hop'].append(float(hop))
        time_perf,datasize_tx,bitrate=doIperf(net,src,dst)
        print 'Throughput ',bitrate,' for ',pair
        result['throughput'].append(float(bitrate))
        link_fail_dict[link_to_fail]=net.addLink("s%d" %link_to_fail[0],"s%d" %link_to_fail[1])
    print 'Average Number of Hop:', getavg(result['hop'])
    print 'Average Delay: ', getavg(result['delay'])
    print 'Throughput:',getavg(result['throughput'])
    CLI(net)
    net.stop()
if __name__ == '__main__':
    setLogLevel( 'info' )
    runner()      
