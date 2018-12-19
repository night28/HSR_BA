import napalm
import json
import dnac
import os
from flask import Flask, render_template, request, flash, redirect
from flask_wtf import FlaskForm
from wtforms import StringField,IntegerField, SubmitField, SelectMultipleField, SelectField, HiddenField
from wtforms.validators import DataRequired


app = Flask(__name__, static_url_path='/static')
SECRET_KEY = os.urandom(32)
app.config['SECRET_KEY'] = SECRET_KEY


def get_virtual_networks():
    virtual_networks = []
    for virtual_network in dnac.get(api='data/customer-facing-service/virtualnetworkcontext', ver='v2').json()['response']:
        virtual_networks.append(VirtualNetwork(virtual_network))
    return virtual_networks


def get_fabrics():
    fabrics = []
    for fabric in dnac.get(api='data/customer-facing-service/ConnectivityDomain?domainType=FABRIC_LAN', ver='v2').json()['response']:
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
        for site in dnac.get(api='data/customer-facing-service/summary/ConnectivityDomain?cdFSiteList={}'.format(fabric), ver='v2').json()['response'][0]['fabricSiteSummary']:
            print site
            sites.append(Site(site))
        return sites
    return None


class NetworkDevice:
    def __init__(self, device):
        self.id = device['id']
        self.hostname = device['hostname']


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
        self.ip_pools = []

    def get_ip_pools(self):
        pool_ids = []
        for pool_id in dnac.get(api='commonsetting/global/{}'.format(self.id), params={'key':'.*ip.pool..*'}).json()['response']:
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
                print 'VN {} has no scalable Group'.format(self.name)
                continue



@app.route('/')
def net_overview():
    network_devices = []
    for device in get_devices():
        network_devices.append(NetworkDevice(device))
    return render_template('index.html', devices=network_devices)


@app.route('/virtual_networks')
def virtual_network_overview():
    virtual_networks = []
    scalable_groups = []
    virtual_networks = get_virtual_networks()
    # for scalable_group in get_scalable_groups():
    #     scalable_groups.append(ScalableGroup(scalable_group))
    for network in virtual_networks:
        print network.name
    return render_template('virtual_networks.html', virtual_networks=virtual_networks, scalable_groups=scalable_groups)

@app.route('/show_config/<device>')
def show_config(device):
    network_device = NetworkDevice(dnac.get(api='network-device', params={'hostname': device}).json()['response'][0])
    config = dnac.get(api='network-device/' + network_device.id + '/config').json()['response']
    return render_template('config.html', device=network_device, config=config)


@app.route('/add_vn', methods=['GET', 'POST'])
def add_vn():
    if 'step' not in request.form:
        print get_fabrics_for_form()
        return render_template('add_vn.html', step='1', fabrics=get_fabrics_for_form())
    elif request.form['step'] == '2':
        print 'Step 2'
        selected_fabric = str(request.form['fabric'])
        selected_vnname = str(request.form['vnname'])
        sites = get_sites_for_fabric(selected_fabric)
        return render_template('add_vn.html', step='2', sites=sites, selected_fabric=selected_fabric, selected_vnname=selected_vnname)
    elif request.form['step'] == '3':
        print 'Step3'
        selected_sites = request.form.getlist('selected_sites')
        selected_fabric = request.form['selected_fabric']
        selected_vnname = request.form['selected_vnname']
        sites = get_sites_for_fabric(selected_fabric)
        new_sites = []
        print 'Selected Sites: {}'.format(selected_sites)
        for site in sites:
            if site.id in selected_sites:
                print 'Site: {}'.format(site.id)
                site.get_ip_pools()
                print 'Site: {}'.format(site.name)
                print 'IP_Pool: {}'.format(site.ip_pools)
                new_sites.append(site)
        return render_template('add_vn.html', step='3', sites=new_sites, selected_fabric=selected_fabric, selected_vnname=selected_vnname, selected_sites=selected_sites)
    elif request.form['step'] == '4':
        print 'Step4'
        selected_sites = request.form['selected_sites']
        selected_fabric = request.form['selected_fabric']
        selected_vnname = request.form['selected_vnname']
        selected_ip_pools = {}
        for site in selected_sites:
            selected_ip_pools[site] = request.form[site + '_ip_pool']
        print selected_ip_pools
        return render_template('add_vn.html', step='4', selected_fabric=selected_fabric, selected_vnname=selected_vnname)



@app.route('/add_ip_pool')
def add_ip_pool():
    form = AddIPPoolForm()
    return render_template('add_ip_pool.html', form=form)


def get_areas():
    areas = []
    sites = dnac.get(api='topology/site-topology').json()['response']['sites']
    for site in sites:
        if site['locationType'] == 'area':
            areas.append(site['name'])
    return areas


def get_devices():
    devices = dnac.get(api='network-device').json()['response']
    print devices
    return devices


def get_scalable_groups(group_id=''):
    scalable_groups = []
    for scalable_group in dnac.get(api = 'data/customer-facing-service/scalablegroup/' + group_id, ver='v2').json()['response']:
        try:
            scalable_groups.append(ScalableGroup(scalable_group))
        except Exception as e:
            print e
            continue
    return scalable_groups


if __name__ == '__main__':
    app.run()

