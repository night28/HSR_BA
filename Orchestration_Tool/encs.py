"""
This script provides a function to get ENCS session
and functions to make ENCS REST APIs request
All required modules are imported in this script so from other scripts just need to import this script
"""
import json
import sys

import requests   # We use Python external "requests" module to do HTTP query
import config  # ENCS IP is assigned in config.py

# It's used to get rid of certificate warning messages when using Python 3.
# For more information please refer to: https://urllib3.readthedocs.org/en/latest/security.html
requests.packages.urllib3.disable_warnings() # Disable warning message


def get_session(uname=config.ENCS_USER, pword=config.ENCS_PASSWORD):
    """
    This function returns a new service token.
    Passing ip, version, username, and password when used as standalone function
    to overwrite the configuration above.

    Parameters
    ----------
    uname (str): user name to authenticate with
    pword (str): password to authenticate with

    Return:
    -------
    str: ENCS authentication token
    """
    s = requests.Session()
    s.auth = (uname, pword)
    s.headers = ({'Content-type': 'application/vnd.yang.data+json', 'Accept': 'application/vnd.yang.data+json'})
    s.verify = False
    return s


def get(ip=config.ENCS_IP, api=''):
    """
    To simplify requests.get with default configuration.Return is the same as requests.get

    Parameters
    ----------
    ip (str): encs routable DNS address or ip
    api (str): encs api without prefix

    Return:
    -------
    object: an instance of the Response object(of requests module)
    """
    session = get_session()
    url = "https://"+ip+"/api/"+api
    print ("\nExecuting GET '%s'\n"%url)
    try:
    # The request and response of "GET" request
        resp = session.get(url)
        print ("GET '%s' Status: "%api,resp.status_code,'\n') # This is the http request status
        return resp
    except:
       print ("Something wrong with GET /",api)
       sys.exit()


def post(ip=config.ENCS_IP, api='', data=''):
    """
    To simplify requests.post with default configuration. Return is the same as requests.post

    Parameters
    ----------
    ip (str): encs routable DNS address or ip
    api (str): encs api without prefix
    data (JSON): JSON object

    Return:
    -------
    object: an instance of the Response object(of requests module)
    """
    session = get_session()
    url = "https://"+ip+"/api/"+api
    print ("\nExecuting POST '%s'\n"%url)
    try:
    # The request and response of "POST" request
        resp = session.post(url, data)
        print ("POST '%s' Status: "%api,resp.status_code,'\n') # This is the http request status
        return(resp)
    except:
       print ("Something wrong with POST /",api)
       sys.exit()
