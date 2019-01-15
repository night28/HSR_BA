import json
import dnac
import encs
import os
import time
import shlex
import git
import config
import shutil
import re
import requests
import netaddr
from jinja2 import Environment
from jinja2 import FileSystemLoader
from ncclient import manager
from flask import Flask, render_template, request

app = Flask(__name__, static_url_path='/static')
SECRET_KEY = os.urandom(32)
app.config['SECRET_KEY'] = SECRET_KEY


def get_virtual_networks():
    virtual_networks = []
    for virtual_network in dnac.get(api='data/customer-facing-service/virtualnetworkcontext', ver='v2').json()[
        'response']:
        virtual_networks.append(VirtualNetwork(virtual_network))
    return virtual_networks


def get_fabrics():
    fabrics = []
    for fabric in \
            dnac.get(api='data/customer-facing-service/ConnectivityDomain?domainType=FABRIC_LAN', ver='v2').json()[
                'response']:
        fabrics.append(Fabric(fabric))
    return fabrics


def get_fabrics_for_form():
    fabrics = []
    for fabric in get_fabrics():
        fabrics.append((fabric.id, fabric.name))
    return fabrics


def get_sites_for_fabric(fabric):
    sites = []
    if fabric:
        for site in \
                dnac.get(api='data/customer-facing-service/summary/ConnectivityDomain?cdFSiteList={}'.format(fabric),
                         ver='v2').json()['response'][0]['fabricSiteSummary']:
            print site
            sites.append(Site(site))
        return sites
    return None


def wait_for_task(task_id):
    while True:
        response = dnac.get(api='task/{}'.format(task_id), ver='v1').json()['response']
        if 'data' in response:
            finished = dict(token.split('=') for token in shlex.split(response['data'].replace(';', ' ')))[
                'processcfs_complete']
            if finished == 'true':
                break
        elif 'endTime' in response:
            file = response['progress'].split(':')[1].strip('}').strip('"')
            return dnac.get(api='file/{}'.format(file), ver='v1')
        time.sleep(1)
    response = dict(token.split('=') for token in shlex.split(
        dnac.get(api='task/{}'.format(task_id), ver='v1').json()['response']['data'].replace(';', ' ')))['cfs_id']
    return response


def create_virtual_network(name):
    payload = [{'name': name, 'virtualNetworkContextType': 'ISOLATED'}]
    task_id = \
        dnac.post(api='data/customer-facing-service/virtualnetworkcontext', ver='v2', data=payload).json()['response'][
            'taskId']
    print 'Task ID: {}'.format(task_id)
    print dnac.get(api='task/{}'.format(task_id), ver='v1').json()['response']
    vn_id = wait_for_task(task_id)
    print 'VN ID: {}'.format(vn_id)
    return vn_id


def get_border_for_site(site, siteid):
    border_nodes = []
    nodes = dnac.get(api='data/device-config-status?cfsNamespace={}&isLatest=true'.format(site), ver='v2').json()[
        'response']
    for node in nodes:
        print node
        if node['role'] == 'BORDER ROUTER':
            border_nodes.append(BorderNode(node, siteid))
    return border_nodes


def get_vlan_interfaces(device):
    interfaces = []
    interfaces = dnac.get(api='network-device/{}/vlan'.format(device.deviceId)).json()['response']
    for interface in interfaces:
        print interface
        if 'vlanType' in interface and interface['vlanType'] == 'vrf interface to External router':
            device.vlanInterfaces.append(VlanInterface(interface))


def get_devices():
    devices = []
    for device in dnac.get(api='network-device').json()['response']:
        devices.append(NetworkDevice(device))
    return devices


def get_scalable_groups(group_id=''):
    scalable_groups = []
    for scalable_group in dnac.get(api='data/customer-facing-service/scalablegroup/' + group_id, ver='v2').json()[
        'response']:
        try:
            scalable_groups.append(ScalableGroup(scalable_group))
        except Exception as e:
            print e
            continue
    return scalable_groups


def get_segment_id(site, vn, fabric):
    segment = ''
    # dnac.get(api='data/customer-facing-service/VirtualNetwork?name=.*{}.*'.format(fabric.name), ver='v2').json()['response']:
    return segment


def assign_ip_pool_to_virtual_network(ippool, segment, site):
    # payload = []
    # task_id = dnac.put(api='data/customer-facing-service/VirtualNetwork', ver='v2', data=payload).json()['response']['taskId']
    # wait_for_task(task_id)
    return 0


def create_xml_config(interface_template, interface, int_id, vlan, ip, mask):
    """Function to render XML document to configure interface from Jinja2."""
    # Use the Jinja2 template provided to create the XML config
    env = Environment(loader=FileSystemLoader('netconf_templates'))
    template = env.get_template(interface_template)
    rendered = template.render(base=interface, interface_id=int_id,
                               vlan_id=vlan, ip=ip, subnet_mask=mask)
    return rendered
    # save the results to the XML file passed as an argument
    with open(xml_file, "wb") as f:
        f.write(rendered)

    # exit if the file hasn't been created
    if os.path.isfile(xml_file) is not True:
        print("Failed to create the XML config file!")
        sys.exit()

class NetworkDevice(object):
    def __init__(self, device):
        self.id = device['id']
        self.managementIpAddress = device['managementIpAddress']
        self.hostname = device['hostname']
        self.vlanInterfaces = []
        self.externalInterfaces = []
        if 'deviceId' in device:
            self.deviceId = device['deviceId']


class BorderNode(NetworkDevice):
    def __init__(self, device, siteId):
        super(BorderNode, self).__init__(device)
        self.siteId = siteId
        self.extConnectivitySettings = []
        self.asNumber = None

    def get_ext_connectivity_settings(self):
        print self.siteId
        for i in \
                dnac.get(api='data/customer-facing-service/DeviceInfo?siteDeviceList={}'.format(self.siteId),
                         ver='v2').json()[
                    'response']:
            if 'BORDERNODE' in i['roles'] and self.deviceId == i['networkDeviceId']:
                print '###################################'
                print i
                self.asNumber = i['deviceSettings']['internalDomainProtocolNumber']
                self.extConnectivitySettings.append(i['deviceSettings']['extConnectivitySettings'])
        for i in self.extConnectivitySettings:
            for j in i:
                self.externalInterfaces.append(ExternalInterface(j))

    def get_fusion_router(self):
        for interface in self.externalInterfaces:
            taskId = dnac.post(api='network-device-poller/cli/read-request',
                               data={"name": "command-runner", "deviceUuids": ["{}".format(self.deviceId)],
                                     "commands": ["show cdp neighbor {}".format(interface.name)]}, ver='v1').json()[
                'response']['taskId']
            print '######## taskID {}:'.format(taskId)
            response = wait_for_task(taskId).json()[0]['commandResponses']['SUCCESS']['show cdp neighbor {}'.format(interface.name)]
            print response.splitlines()
            interface.peer = response.splitlines()[6].split()[0]
            interface.peerInterface = ''.join(response.splitlines()[7].split()[-2::])
            print interface.peer
            print interface.peerInterface
            print interface.remoteAsNumber
            print interface.l3Handoffs

    def configure_peers(self, vnId):
        for i in self.externalInterfaces:
            print '##### {}'.format(self.hostname)
            print i.name
            print i.peer
            print i.peerInterface
            for j in i.l3Handoffs:
                print j
                continue
            if j == 'blah':
                if vnId == j['virtualNetwork']['idRef']:
                    remoteAddress = j['remoteIpAddress']
                    vlanId = j['vlanId']
                interface = filter(None, re.split(r'(\d+.*)', i.peerInterface))
                print interface
                ip = netaddr.IPNetwork(j['remoteIpAddress'])
                interfaceConfig = create_xml_config('subinterface.j2', interface[0], interface[1], j['vlanId'], ip.ip, ip.netmask)
                # open the NETCONF session
                with manager.connect(host=i.peer, port=830, username=config.NETWORK_USER, password=config.NETWORK_PASSWORD, hostkey_verify=False, device_params={'name':'csr'}) as m:
                    try:
                        # issue the edit-config operation with the XML config
                        print interfaceConfig
                        rpc_reply = m.edit_config(target='running', config=interfaceConfig)
                        print rpc_reply
                    except Exception as e:
                        print("Encountered the following RPC error!")
                        print(e)
                        # validate the RPC Reply returns "ok"
                    if rpc_reply.ok is not True:
                        print("Encountered a problem when configuring the device!")



class ExternalInterface:
    def __init__(self, settings):
        self.name = settings['interfaceUuid']
        self.remoteAsNumber = settings['externalDomainProtocolNumber']
        self.l3Handoffs = []
        self.peer = ''
        self.peerInterface = ''
        for handoff in settings['l3Handoff']:
            self.l3Handoffs.append(handoff)


class Peer:
    def __init__(self, hostname, interface):
        self.hostname = hostname
        self.interface = interface


class VlanInterface:
    def __init__(self, interface):
        self.vlanNumber = interface['vlanNumber']
        self.ipAddress = interface['ipAddress']
        self.interfaceName = interface['interfaceName']
        self.prefix = interface['prefix']


class ScalableGroup:
    def __init__(self, group):
        self.id = group['id']
        self.name = group['name']
        self.securityGroupTag = group['securityGroupTag']


class Fabric:
    def __init__(self, fabric):
        self.id = fabric['id']
        self.name = fabric['name']


class Site:
    def __init__(self, site):
        self.id = site['siteId']
        self.name = site['siteName']
        self.fabricSiteUuid = site['fabricSiteUuid']
        self.border_nodes = []
        self.ip_pools = []

    def get_ip_pools(self):
        pool_ids = []
        for pool_id in dnac.get(api='commonsetting/global/{}'.format(self.id), params={'key': '.*ip.pool..*'}).json()[
            'response']:
            if pool_id['value'][0]['objReferences'][0]:
                print pool_id['value'][0]['objReferences'][0]
                pool_ids.append(pool_id['value'][0]['objReferences'][0])
        print pool_ids
        params = ''
        for i in pool_ids:
            params += ('instanceUuid=' + i + '&')
        params.rstrip('&')
        print 'Params: {}'.format(params)
        for pool in dnac.get(api='ippool?{}'.format(params), ver='v2').json()['response']:
            print pool
            self.ip_pools.append(IPPool(pool))


class IPPool:
    def __init__(self, ip_pool):
        self.id = ip_pool['id']
        self.name = ip_pool['ipPoolName']
        self.network = ip_pool['ipPoolCidr'].split('/')[0]
        self.netmask = ip_pool['ipPoolCidr'].split('/')[1]
        if ip_pool['gateways']:
            self.gateway = ip_pool['gateways'][0]
        if ip_pool['dhcpServerIps']:
            self.dhcpServerIps = ip_pool['dhcpServerIps']
        if ip_pool['dhcpServerIps']:
            self.dnsServerIps = ip_pool['dnsServerIps']


class VirtualNetwork:
    def __init__(self, network):
        self.id = network['id']
        self.name = network['name']
        self.scalable_groups = []
        for scalable_group in network['scalableGroup']:
            try:
                self.scalable_groups.append(get_scalable_groups(scalable_group['idRef'])[0])
            except IndexError:
                continue


class VirtualMachine:
    def __init__(self, vm):
        self.name = vm['name']
        self.image = vm['image']
        self.flavor = vm['flavor']
        self.networks = []
        if 'interfaces' in vm:
            for network in vm['interfaces']['interface']:
                self.networks.append(network['network'])
        self.state = self.get_state()

    def get_state(self):
        state = \
            encs.get(
                api='operational/vm_lifecycle/opdata/tenants/tenant/admin/deployments/{}'.format(self.name)).json()[
                'vmlc:deployments']['state_machine']['state']
        if state == 'SERVICE_ACTIVE_STATE':
            return 'Up'
        return 'Down'


@app.route('/')
def net_overview():
    return render_template('index.html', devices=get_devices())


@app.route('/virtual_networks')
def virtual_network_overview():
    virtual_networks = []
    scalable_groups = []
    virtual_networks = get_virtual_networks()
    # for scalable_group in get_scalable_groups():
    #     scalable_groups.append(ScalableGroup(scalable_group))
    return render_template('virtual_networks.html', virtual_networks=virtual_networks, scalable_groups=scalable_groups)


@app.route('/show_config/<device>')
def show_config(device):
    network_device = NetworkDevice(dnac.get(api='network-device', params={'hostname': device}).json()['response'][0])
    configuration = dnac.get(api='network-device/' + network_device.id + '/config').json()['response']
    return render_template('config.html', device=network_device, config=configuration)


@app.route('/add_vn', methods=['GET', 'POST'])
def add_vn():
    if 'step' not in request.form:
        return render_template('add_vn.html', step='1', fabrics=get_fabrics_for_form())
    elif request.form['step'] == '2':
        selected_fabric = str(request.form['fabric'])
        selected_vnname = str(request.form['vnname'])
        sites = get_sites_for_fabric(selected_fabric)
        return render_template('add_vn.html', step='2', sites=sites, selected_fabric=selected_fabric,
                               selected_vnname=selected_vnname)
    elif request.form['step'] == '3':
        selected_sites = request.form.getlist('selected_sites')
        selected_fabric = request.form['selected_fabric']
        selected_vnname = request.form['selected_vnname']
        sites = get_sites_for_fabric(selected_fabric)
        new_sites = []
        for site in sites:
            if site.id in selected_sites:
                site.get_ip_pools()
                new_sites.append(site)
        sites_count = len(new_sites)
        return render_template('add_vn.html', step='3', sites=new_sites, selected_fabric=selected_fabric,
                               selected_vnname=selected_vnname, sites_count=sites_count)
    elif request.form['step'] == '4':
        selected_sites = []
        selected_fabric = request.form['selected_fabric']
        selected_vnname = request.form['selected_vnname']
        sites_count = int(request.form['sites_count'])
        for i in range(0, sites_count, 1):
            selected_sites.append(request.form['selected_site_' + str(i)])
        selected_ip_pools = {}
        for site in selected_sites:
            selected_ip_pools[site] = request.form[site + '_ip_pool']
        print 'Selected VN Name: {}'.format(selected_vnname)
        print 'Selected Fabric: {}'.format(selected_fabric)
        print 'Selected Sites: {}'.format(selected_sites)
        print 'Selected IP Pools: {}'.format(selected_ip_pools)
        #vn_id = create_virtual_network(selected_vnname)
        sites = []
        for site in get_sites_for_fabric(selected_fabric):
            if site.id in selected_sites:
                sites.append(site)
        for site in sites:
            for border_node in get_border_for_site(site.fabricSiteUuid, site.id):
                border_node.get_ext_connectivity_settings()
                print border_node.hostname
                print border_node.id
                print border_node.deviceId
                border_node.get_fusion_router()
                site.border_nodes.append(border_node)
                for ext in border_node.externalInterfaces:
                    print ext.l3Handoffs
                #border_node.configure_peers(vn_id)
        #for site in sites:
        #    for border_node in site.border_nodes:
        #        get_vlan_interfaces(border_node)
        #for site in sites:
        #    segment = get_segment_id(site, selected_vnname, selected_fabric)
        #    assign_ip_pool_to_virtual_network(selected_ip_pools, segment, site)
        #    for border_node in site.border_nodes:
        # for site in sites:
        #     print "Site: {}".format(site.name)
        #     for node in site.border_nodes:
        #         print "Border Node: {}".format(node.hostname)
        #         print "Vlan Interfaces {}".format(node.vlanInterfaces)
        #         for interface in node.vlanInterfaces:
        #             print interface.vlanNumber
        return render_template('add_vn.html', step='4', selected_vnname=selected_vnname, selected_sites=sites,
                               selected_ip_pools=selected_ip_pools)


@app.route('/virtual_machines', methods=['GET', 'POST'])
def virtual_machines():
    vms = []
    for deployment in \
            encs.get(api='config/vm_lifecycle/tenants/tenant/admin/deployments?deep').json()['vmlc:deployments'][
                'deployment']:
        vms.append(VirtualMachine(deployment['vm_group'][0]))
    if 'action' not in request.form:
        return render_template('virtual_machines.html', vms=vms)
    else:
        action = request.form['action']
        vm = request.form['vm']
        if action == 'Start':
            data = {"vmAction": {"actionType": "START", "vmName": vm}}
        else:
            data = {"vmAction": {"actionType": "STOP", "vmName": vm}}
        print encs.post(api='operations/vmAction', data=json.dumps(data))
        return render_template('virtual_machines.html', vms=vms)


@app.route('/configuration_history', methods=['GET'])
def config_history():
    if os.path.exists(config.REPO_PATH):
        shutil.rmtree(config.REPO_PATH)
    os.makedirs(config.REPO_PATH)
    repo = git.Repo.init(config.REPO_PATH)
    origin = repo.create_remote('origin', config.CONFIG_REPO)
    origin.fetch()
    origin.pull(origin.refs[0].remote_head)
    commits = []
    for commit in repo.iter_commits():
        commits.append(commit)
        print commit.hexsha
        print commit.committed_datetime
        print commit.message
    return render_template('config_history.html')


if __name__ == '__main__':
    app.run()
