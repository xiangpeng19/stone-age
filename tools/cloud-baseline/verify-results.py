from pathlib import Path
import json
logs=Path('logs')
for name in ['saac-start','gmsv-start']:
 (logs/(name+'.txt')).write_text((logs/(name+'.raw')).read_bytes().decode('gb18030',errors='replace'))
rows=(logs/'runtime-tcp.txt').read_text().splitlines()[1:]
listeners=[r.split()[1] for r in rows if r.split()[3]=='0A']
expected={'0100007F:33FA','0100007F:4A79','0100007F:4B64'}
checks={
'saac_event_loop':'开始工作' in (logs/'saac-start.txt').read_text(),
'gmsv_account_handshake':'与AC服务器连接成功' in (logs/'gmsv-start.txt').read_text(),
'processes_survived':'PROCESSES_SURVIVED' in (logs/'runtime-result.log').read_text(),
'only_expected_loopback_listeners':set(listeners)==expected,
'no_external_interface':all(':' not in l or l.strip().startswith('lo:') for l in (logs/'runtime-network.txt').read_text().splitlines()),
'no_route':len((logs/'runtime-network.txt').read_text().split('Iface')[1].strip().splitlines())==1,
}
result={'scope':'compile and isolated startup/handshake only','checks':checks,'passed':all(checks.values()),'not_tested':['game client login','character creation','battle','trade','save reload','concurrency','long duration stability','full security'],'warning_count':{p.name:p.read_bytes().count(b'warning:') for p in [logs/'saac-build-1.log',logs/'gmsv-build-2.log']}}
(logs/'test-results.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2));assert result['passed']
