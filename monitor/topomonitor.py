import networkx as nx
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import CPULimitedHost
from mininet.link import TCLink
from mininet.node import Controller, RemoteController
from mininet.cli import CLI
from mininet.log import setLogLevel
import re

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
def runner():
    "Create and run a custom topo with adjustable link parameters"
    topo = CompleteGraphTopo( )
    c = RemoteController('c', '127.0.0.1', 6633)
    net = Mininet( topo=topo,
                   controller=None,
	           host=CPULimitedHost, link=TCLink ,waitConnected=True,autoSetMacs=True)

    net.addController(c)	           
    net.start() 
    CLI(net)
    test_pair=[(0,7),(3,8),(0,9),(8,6),(9,1)]
    result={'hop':[],'delay':[],'throughput':[]}
    for pair in test_pair:
        host1,host2=pair
        src=net.getNodeByName('h'+str(host1+1))
        dst=net.getNodeByName('h'+str(host2+1))
        sent,received,min_,avg=ping(net,[src,dst],1024,2)
        print 'Delay ',avg,' for ',pair
        result['delay'].append(float(avg))
        hop=get_path_length(net,src,dst)
        print 'Hop ',hop,' for ',pair
        result['hop'].append(float(hop))
        time,datasize_tx,bitrate=doIperf(net,src,dst)
        print 'Throughput ',bitrate,' for ',pair
        result['throughput'].append(float(bitrate))
    print 'Average Number of Hop:', getavg(result['hop'])
    print 'Average Delay: ', getavg(result['delay'])
    print 'Throughput:',getavg(result['throughput'])
    CLI(net)
    net.stop()
if __name__ == '__main__':
    setLogLevel( 'info' )
    runner()      
#topos = { 'completeTopo':(lambda:CompleteGraphTopo())}
