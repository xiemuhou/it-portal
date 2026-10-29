"""Save a rollback snapshot of the ledger tables before an additive migration."""
from datetime import datetime
from pathlib import Path
import json
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import sqlalchemy as sa
from portal.database import settings,database_url,make_engine,TABLES as T,jsonable

config=settings();engine=make_engine(database_url(config))
names=['sites','locations','vendors','resources','network_scopes','devices','device_identifiers','device_interfaces','device_endpoints','device_relations','circuits','circuit_endpoints','vlans','subnets','subnet_gateways','wifi_networks','wifi_vlan_bindings','vpn_connections','vpn_tunnels','vpn_routes','ledger_profiles','ledger_links']
folder=Path(config['data_dir'])/'ledger-backups'/datetime.now().strftime('%Y%m%d-%H%M%S-%f');folder.mkdir(parents=True)
with engine.connect() as conn:
    present=set(sa.inspect(conn).get_table_names());counts={}
    for name in names:
        if name not in present:continue
        values=conn.execute(sa.select(T[name])).mappings().all();counts[name]=len(values)
        (folder/(name+'.json')).write_text(json.dumps(jsonable(values),ensure_ascii=False,indent=2),encoding='utf-8')
    (folder/'manifest.json').write_text(json.dumps({'created_at':datetime.now().isoformat(),'tables':counts},indent=2),encoding='utf-8')
engine.dispose();print('Ledger snapshot saved:',folder);print('Resource count:',counts.get('resources',0))
