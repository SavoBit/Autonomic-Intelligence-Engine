#!/usr/bin/env python3


import time
import xml.dom.minidom
import xml.etree.ElementTree

from lxml import etree

import requests


def create_TAL(tal_rule_name, mon_metric, metric_dimensions):
    #TODO: Make custome TAL-Script creator with App-Cat/-Inv connectivity
    schemalocation = "tal.cse.com tal.xsd"
    xsi = "http://www.w3.org/2001/XMLSchema-instance"
    ns = {"xsi": xsi}
    tal = etree.Element("tal", attrib={"xmlns":"tal.cse.com", "{"+ xsi +"}schemaLocation" : "tal.cse.com tal.xsd"}, nsmap=ns)

    reaction = etree.SubElement(tal, "reaction")
    diagnosis = etree.SubElement(reaction, "diagnosis")

    symptom = etree.SubElement(diagnosis, "symptom", OID="{}".format(tal_rule_name))
    analysis = etree.SubElement(symptom, "analysis")
    aggregation = etree.SubElement(analysis, "aggregation")
    aggregation_item = etree.SubElement(aggregation, "aggregationItem", OID="From Service Catalogue")
    aggregation_rule = etree.SubElement(aggregation_item, "aggregationRule", OID="", description="")
    metric = etree.SubElement(aggregation_rule, "metric")
    name = etree.SubElement(metric, "name")
    parameter = etree.SubElement(name, "parameter")
    etree.SubElement(parameter, "OID").text = "Number"
    etree.SubElement(parameter, "name").text = mon_metric
    dimensions = etree.SubElement(metric, "dimensions")
    for d in metric_dimensions:
        para = etree.SubElement(dimensions, "parameter")
        etree.SubElement(para, "OID").text = d[0]
        etree.SubElement(para, "name").text = d[1]
        if len(d) == 3:
            etree.SubElement(para, "value").text = d[2]

    causes = etree.SubElement(diagnosis, "causes")
    etree.SubElement(causes, "cause", causeOID="bot.net", description="Classified as bot-traffic", likelihood="0.99")

    tactic = etree.SubElement(reaction, "tactic", description="Activate DPI", id="DPI", priority="1")
    etree.SubElement(tactic, "cause", causeOID="bot.net", description="Botnet Suspected")
    action = etree.SubElement(tactic, "action", id="dpi.operation", order="1")
    actionopt = etree.SubElement(action, "actionOption", operation="drop", typeOfOption="add")
    actuator = etree.SubElement(actionopt, "actuator", OID="FlowT")
    
    acc_conf = {("IP","srcIpAddress","SourceIP"),
              ("IP","dstIpAddress","DestinationIP"),
              ("Number","dstPort","DestinationPort"),
              ("Text","ServiceID","ServiceID")}


    configuration = etree.SubElement(actuator, "configuration")
    for d in acc_conf:
        param = etree.SubElement(configuration, "parameter")
        etree.SubElement(param, "OID").text = d[0]
        etree.SubElement(param, "name").text = d[1]
        etree.SubElement(param, "value").text = d[2]

    metadata = etree.SubElement(action, "metadata")
    params = etree.SubElement(metadata, "parameter")
    etree.SubElement(params, "OID").text = "MAPPING"
    etree.SubElement(params, "name").text = "drop"
    etree.SubElement(params, "value").text = "dropFlows"

    loc = etree.SubElement(metadata, "location")
    cltodest = etree.SubElement(loc, "closeToSource")
    parame = etree.SubElement(cltodest, "parameter")
    etree.SubElement(parame, "name").text="dummy"

    return tal

def disable_oldscripts(script,tenant="alksd"):
    headers = {'Content-type' : 'application/xml','Accept' : 'application/json'}
    task_url = 'http://192.168.89.128:18183/tal/engine/'+tenant
    r = requests.put(task_url+"/"+script+"/disable", headers=headers)
    print(task_url+"/"+script+"/disable")


def enable_oldscripts(script, tenant="alksd"):
    headers = {'Content-type' : 'application/xml','Accept' : 'application/json'}
    task_url = 'http://192.168.89.128:18183/tal/engine/'+tenant
    r = requests.put(task_url+"/"+script+"/enable", headers=headers)
    print(task_url+"/"+script+"/enable")


def write_file(tal_rule_name,xmlstr):
    with open ('output/{}.xml'.format(tal_rule_name), "w") as f:
        f.write(xmlstr)
    #pass

def remove_tal(rulename, tenant="alksd"):
    headers = {'Content-type' : 'application/xml','Accept' : 'application/json'}
    task_url = 'http://192.168.89.128:18183/tal/engine/'+tenant+'/'+rulename
    r = requests.delete(task_url, headers=headers)
    print (r.text)

def trigger_script(rulename, json):
    headers = {'Content-type' : 'application/json','Accept' : 'application/json'}
    task_url = 'http://192.168.89.128:19000/'+rulename
    r = requests.post(task_url, json=json, headers=headers)
    print("Triggering {!r},  Status code: {!r}, Text: {!r}".format(rulename,r.status_code,r.text))

def send_tal(xml, rulename, tenant="alksd"):
    headers = {'Content-type' : 'application/xml','Accept' : 'application/json'}
    task_url = 'http://192.168.89.128:18183/tal/engine/'+tenant
    print(task_url)
    r = requests.post(task_url, data=xml, headers=headers)
    if r.status_code == 201:
        print("TAL-Script created")
    else:
        if r.status_code == 409:
            print("Text: {}".format(r.text))
            remove_tal(rulename)
            print("Add a new")
            send_tal(xml,rulename)
        else:
            print("Error sending Task: {} \n {}".format(r.status_code,r.text))   



def test_enable_disable():
    scripts = "SP_LOOP_II"
    print("Enabling SP_LOOP_II")
    enable_oldscripts("SP_LOOP_II")
    print("sleeping")
    time.sleep(10) 
    print("disabling SP_LOOP_II")
    disable_oldscripts(scripts)


def test_xml_creation():
    tal_rule_name = "TEST_GEN"
    mon_metric = "random_metric"
    metric_dimensions = {("IP","SourceIP"),
                         ("IP","DestinationIP"),
                         ("Number","DestinationPort", "80")}
    symptom = create_TAL(tal_rule_name, mon_metric, metric_dimensions)
    xmlstr = xml.dom.minidom.parseString(xml.etree.ElementTree.tostring(symptom)).toprettyxml(indent="    ")
    write_file(tal_rule_name,xmlstr)


def test_tal_push():
    tal_rule_name = "SP_LOOP_III_TEST"
    mon_metric = "loop_3_test"
    metric_dimensions = {("IP","SourceIP"),
                         ("IP","DestinationIP"),
                         ("Number","DestinationPort", "80")}

    remove_tal(tal_rule_name)
    print("Removed {}".format(tal_rule_name))
    time.sleep(10)
    symptom = create_TAL(tal_rule_name, mon_metric, metric_dimensions)
    xmlstr = xml.dom.minidom.parseString(xml.etree.ElementTree.tostring(symptom)).toprettyxml(indent="    ")
    write_file(tal_rule_name,xmlstr)
    print("Sending generated {}".format(tal_rule_name))
    send_tal(xmlstr,tal_rule_name)


def test_tal_trigger():
    app_id = '833ca890-2d80-4c4b-81ee-149c6e2f80ca'
    trigger_script("SH_LOOP_II", {
                                'Degradation':'dummy',
                                'appId': app_id,
                            })

