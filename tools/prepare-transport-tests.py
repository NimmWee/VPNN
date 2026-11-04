"""Generate owner-only test configurations without printing credentials or call links."""
import copy
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
private = root/'private'/'transport-test'
private.mkdir(parents=True,exist_ok=True)
owner = json.loads((root/'private'/'transport-owner.json').read_text())
call = (root/'private'/'current-call.txt').read_text().strip()

def write(name,data):
    path=private/name
    path.write_text(json.dumps(data,indent=2))
    path.chmod(0o600)

dns={'mode':'dns','listen':'127.0.0.1:19082','dns':{'domains':[owner['domain']], 'resolvers':['1.1.1.1:53','8.8.8.8:53'], 'key':owner['dnsKey'],'encryption':5,'systemResolvers':True}}
write('dns-recursive.json',dns)
direct=copy.deepcopy(dns)
direct['dns']['resolvers']=[owner['server']+':53']
direct['dns']['systemResolvers']=False
write('dns-direct.json',direct)
vk={'mode':'vk','listen':'127.0.0.1:19081','vk':{
    'provider':'vk','peer':owner['server']+':'+str(owner['turnPort']), 'clientId':owner['clientId'],
    'proxy':{'mode':'tcp'},'turn':{'n':6}, 'vk':{'links':[call],'manualCaptcha':True,'autoCaptcha':False,'advancedCaptcha':False},
    'obf':{'profile':'rtpopus3','key':owner['obfKey']}}}
write('vk.json',vk)
direct=copy.deepcopy(vk)
direct['vk']['provider']='direct'
write('vk-direct.json',direct)
write('xray-client.json',{'log':{'loglevel':'warning'},
    'inbounds':[{'listen':'127.0.0.1','port':19090,'protocol':'socks','settings':{'auth':'noauth','udp':False}}],
    'outbounds':[{'protocol':'vless','settings':{'vnext':[{'address':'127.0.0.1','port':19081,'users':[{'id':owner['uuid'],'encryption':'none'}]}]},'streamSettings':{'network':'tcp','security':'none'}}]})

profiles={}
for mode,meta in [('dns',dns),('vk',vk)]:
    proxy={'name':'VPNN','server':'127.0.0.1','port':19082 if mode=='dns' else 19081,'udp':False,'x-vpnn':meta}
    proxy.update({'type':'socks5'} if mode=='dns' else {'type':'vless','uuid':owner['uuid'],'network':'tcp','tls':False})
    profiles[mode]={'proxies':[proxy],'proxy-groups':[{'name':'VPNN mode','type':'select','proxies':['VPNN']}],'rules':['MATCH,VPNN mode']}
    write('profile-'+mode+'.json',profiles[mode])
write('group.json',{'id':'owner-transports','name':'DNS / VK · owner test','calls':[call],'profiles':profiles})
print('Private DNS/VK test configurations prepared. No credentials printed.')
