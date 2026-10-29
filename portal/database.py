"""One explicit logical schema, compiled for SQLite development, SQL Server and MySQL."""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import json
import os
import secrets
import threading
import time
import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import mssql, mysql
from sqlalchemy.engine import URL

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((Path(__file__).parent / 'schema.json').read_text(encoding='utf-8'))
SPECS = {x['name']: x for x in SCHEMA if x['phase'] == 'V1'}
metadata = sa.MetaData(naming_convention={
    'ix': 'ix_%(table_name)s_%(column_0_name)s',
    'uq': 'uq_%(table_name)s_%(column_0_name)s',
    'fk': 'fk_%(table_name)s_%(column_0_name)s',
    'pk': 'pk_%(table_name)s',
})


def utcnow():
    value = datetime.now(timezone.utc)
    return value.replace(tzinfo=None, microsecond=(value.microsecond // 1000) * 1000)


_UUID7_LOCK=threading.Lock()
_UUID7_LAST_MS=-1
_UUID7_SEQUENCE=0

def uid():
    """Generate a sortable UUIDv7-compatible identifier for new rows.

    Existing UUIDv4 values remain valid. Time ordering reduces random inserts and
    page fragmentation in SQL Server/MySQL indexes while retaining 74 random bits.
    """
    global _UUID7_LAST_MS,_UUID7_SEQUENCE
    with _UUID7_LOCK:
        milliseconds=(time.time_ns()//1_000_000)&((1<<48)-1)
        if milliseconds>_UUID7_LAST_MS:_UUID7_LAST_MS=milliseconds;_UUID7_SEQUENCE=secrets.randbits(12)
        else:
            _UUID7_SEQUENCE+=1
            if _UUID7_SEQUENCE>0xFFF:_UUID7_LAST_MS+=1;_UUID7_SEQUENCE=0
            milliseconds=_UUID7_LAST_MS
        sequence=_UUID7_SEQUENCE
    value=(milliseconds<<80)|(0x7<<76)|(sequence<<64)|(0b10<<62)|secrets.randbits(62)
    return str(uuid.UUID(int=value))


def sqltype(kind):
    if kind == 'id':
        return sa.String(36)
    if kind.startswith('a') and kind[1:].isdigit():
        return sa.String(int(kind[1:]))
    if kind.startswith('u') and kind[1:].isdigit():
        return sa.Unicode(int(kind[1:]))
    return {
        'text': sa.UnicodeText(), 'json': sa.UnicodeText(), 'utc': sa.DateTime().with_variant(mssql.DATETIME2(precision=3), 'mssql').with_variant(mysql.DATETIME(fsp=3), 'mysql'),
        'date': sa.Date(), 'bool': sa.Boolean(), 'int': sa.Integer(), 'bigint': sa.BigInteger(),
        'decimal18_2': sa.Numeric(18, 2), 'decimal12_3': sa.Numeric(12, 3),
    }[kind]


TABLES = {}
for name, spec in SPECS.items():
    columns = []
    for f in spec['effective_fields']:
        deferred = f['ref']=='users.id' and f['name'] in ('created_by_user_id','updated_by_user_id','archived_by_user_id','verified_by_user_id')
        args = [sa.ForeignKey(f['ref'], ondelete='NO ACTION', use_alter=deferred)] if f['ref'] else []
        columns.append(sa.Column(f['name'], sqltype(f['type']), *args,
                                 primary_key=f['name'] == spec['pk'], nullable=f['nullable'] if f['name'] != spec['pk'] else False))
    constraints = []
    for i, expr in enumerate(spec['unique'].split(';')):
        if expr.strip():
            constraints.append(sa.UniqueConstraint(*[v.strip() for v in expr.split(',')], name=f'uq_{name}_{i}'))
    TABLES[name] = sa.Table(name, metadata, *columns, *constraints, mysql_charset='utf8mb4')
    for i, expr in enumerate(spec['indexes'].split(';')):
        if expr.strip():
            sa.Index(f'ix_{name}_{i}', *[TABLES[name].c[v.strip()] for v in expr.split(',')])


def _extra_table(name, *columns, constraints=(), indexes=()):
    """Small application-owned tables which are not part of the generic catalog."""
    table = sa.Table(name, metadata, *columns, *constraints, mysql_charset='utf8mb4')
    TABLES[name] = table
    for index_name, fields in indexes:
        sa.Index(index_name, *[table.c[field] for field in fields])
    return table


computer_assets = _extra_table('computer_assets',
    sa.Column('id', sa.String(36), primary_key=True),
    sa.Column('created_at', sqltype('utc'), nullable=False), sa.Column('updated_at', sqltype('utc'), nullable=False),
    sa.Column('created_by_user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='NO ACTION'), nullable=False),
    sa.Column('updated_by_user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='NO ACTION'), nullable=False),
    sa.Column('version', sa.Integer, nullable=False), sa.Column('is_archived', sa.Boolean, nullable=False),
    sa.Column('asset_code', sa.Unicode(64), nullable=False), sa.Column('device_name', sa.Unicode(160), nullable=False),
    sa.Column('device_type', sa.Unicode(64), nullable=False), sa.Column('brand', sa.Unicode(128)),
    sa.Column('model', sa.Unicode(160)), sa.Column('serial_number', sa.Unicode(160)),
    sa.Column('acceptance_month', sa.Date()),
    sa.Column('site_id', sa.String(36), sa.ForeignKey('sites.id', ondelete='NO ACTION'), nullable=False),
    sa.Column('department_id', sa.String(36), sa.ForeignKey('departments.id', ondelete='NO ACTION')),
    sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='NO ACTION')),
    sa.Column('user_name', sa.Unicode(128)), sa.Column('location', sa.Unicode(256)),
    sa.Column('operating_system', sa.Unicode(160)), sa.Column('assignment_type', sa.String(32), nullable=False),
    sa.Column('asset_status', sa.String(32), nullable=False),
    sa.Column('notes', sa.UnicodeText()),
    constraints=(sa.UniqueConstraint('asset_code', name='uq_computer_assets_asset_code'),),
    indexes=(('ix_computer_assets_site_archived', ('site_id','is_archived')),('ix_computer_assets_user', ('user_id',)))
)

computer_network_adapters = _extra_table('computer_network_adapters',
    sa.Column('id', sa.String(36), primary_key=True),
    sa.Column('created_at', sqltype('utc'), nullable=False), sa.Column('updated_at', sqltype('utc'), nullable=False),
    sa.Column('computer_id', sa.String(36), sa.ForeignKey('computer_assets.id', ondelete='NO ACTION'), nullable=False),
    sa.Column('adapter_name', sa.Unicode(128), nullable=False), sa.Column('adapter_type', sa.String(32), nullable=False),
    sa.Column('mac_address', sa.String(17), nullable=False), sa.Column('is_primary', sa.Boolean, nullable=False),
    sa.Column('enabled', sa.Boolean, nullable=False), sa.Column('notes', sa.Unicode(512)),
    constraints=(sa.UniqueConstraint('mac_address', name='uq_computer_network_adapters_mac'),),
    indexes=(('ix_computer_network_adapters_computer', ('computer_id',)),)
)

static_ip_records = _extra_table('static_ip_records',
    sa.Column('id', sa.String(36), primary_key=True),
    sa.Column('created_at', sqltype('utc'), nullable=False), sa.Column('updated_at', sqltype('utc'), nullable=False),
    sa.Column('created_by_user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='NO ACTION'), nullable=False),
    sa.Column('updated_by_user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='NO ACTION'), nullable=False),
    sa.Column('version', sa.Integer, nullable=False),
    sa.Column('vlan_id', sa.String(36), sa.ForeignKey('resources.id', ondelete='NO ACTION'), nullable=False),
    sa.Column('network_id', sa.String(36), nullable=False), sa.Column('ip_address', sa.String(45), nullable=False),
    sa.Column('occupancy_status', sa.String(32), nullable=False), sa.Column('verification_status', sa.String(32), nullable=False),
    sa.Column('assignment_type', sa.String(32), nullable=False),
    sa.Column('department_id', sa.String(36), sa.ForeignKey('departments.id', ondelete='NO ACTION')),
    sa.Column('department_name_snapshot', sa.Unicode(128)),
    sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='NO ACTION')),
    sa.Column('user_name', sa.Unicode(128)), sa.Column('device_type', sa.Unicode(64)),
    sa.Column('computer_id', sa.String(36), sa.ForeignKey('computer_assets.id', ondelete='NO ACTION')),
    sa.Column('adapter_id', sa.String(36), sa.ForeignKey('computer_network_adapters.id', ondelete='NO ACTION')),
    sa.Column('mac_address', sa.String(17)), sa.Column('location', sa.Unicode(256)), sa.Column('notes', sa.UnicodeText()),
    sa.Column('verified_at', sqltype('utc')), sa.Column('verified_by_user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='NO ACTION')),
    constraints=(sa.UniqueConstraint('vlan_id','network_id','ip_address', name='uq_static_ip_records_address'),),
    indexes=(('ix_static_ip_records_network', ('vlan_id','network_id')),('ix_static_ip_records_computer', ('computer_id',)),('ix_static_ip_records_mac', ('mac_address',)))
)

static_ip_history = _extra_table('static_ip_history',
    sa.Column('id', sa.String(36), primary_key=True), sa.Column('created_at', sqltype('utc'), nullable=False),
    sa.Column('ip_record_id', sa.String(36), sa.ForeignKey('static_ip_records.id', ondelete='NO ACTION'), nullable=False),
    sa.Column('actor_user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='NO ACTION'), nullable=False),
    sa.Column('action_code', sa.String(32), nullable=False), sa.Column('snapshot_json', sa.UnicodeText(), nullable=False),
    indexes=(('ix_static_ip_history_record', ('ip_record_id','created_at')),)
)

computer_accessories = _extra_table('computer_accessories',
    sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sqltype('utc'),nullable=False),sa.Column('updated_at',sqltype('utc'),nullable=False),
    sa.Column('computer_id',sa.String(36),sa.ForeignKey('computer_assets.id',ondelete='NO ACTION'),nullable=False),
    sa.Column('accessory_type',sa.Unicode(64),nullable=False),sa.Column('brand_model',sa.Unicode(160)),
    sa.Column('serial_number',sa.Unicode(160)),sa.Column('notes',sa.Unicode(512)),
    indexes=(('ix_computer_accessories_computer',('computer_id',)),))

computer_change_history = _extra_table('computer_change_history',
    sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sqltype('utc'),nullable=False),
    sa.Column('computer_id',sa.String(36),sa.ForeignKey('computer_assets.id',ondelete='NO ACTION'),nullable=False),
    sa.Column('actor_user_id',sa.String(36),sa.ForeignKey('users.id',ondelete='NO ACTION'),nullable=False),
    sa.Column('action_code',sa.String(32),nullable=False),sa.Column('change_summary',sa.Unicode(1000),nullable=False),
    sa.Column('snapshot_json',sa.UnicodeText(),nullable=False),indexes=(('ix_computer_change_history_computer',('computer_id','created_at')),))

consumable_items = _extra_table('consumable_items',
    sa.Column('id',sa.String(36),primary_key=True),
    sa.Column('created_at',sqltype('utc'),nullable=False),sa.Column('updated_at',sqltype('utc'),nullable=False),
    sa.Column('created_by_user_id',sa.String(36),sa.ForeignKey('users.id',ondelete='NO ACTION'),nullable=False),
    sa.Column('updated_by_user_id',sa.String(36),sa.ForeignKey('users.id',ondelete='NO ACTION'),nullable=False),
    sa.Column('version',sa.Integer,nullable=False),sa.Column('is_archived',sa.Boolean,nullable=False),
    sa.Column('item_code',sa.Unicode(64),nullable=False),sa.Column('name',sa.Unicode(160),nullable=False),
    sa.Column('category',sa.Unicode(80)),sa.Column('specification',sa.Unicode(200)),
    sa.Column('unit',sa.Unicode(32),nullable=False),sa.Column('minimum_stock',sa.Numeric(18,2),nullable=False),
    sa.Column('notes',sa.Unicode(1000)),
    constraints=(sa.UniqueConstraint('item_code',name='uq_consumable_items_code'),),
    indexes=(('ix_consumable_items_name',('name','is_archived')),))

consumable_movements = _extra_table('consumable_movements',
    sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sqltype('utc'),nullable=False),
    sa.Column('actor_user_id',sa.String(36),sa.ForeignKey('users.id',ondelete='NO ACTION'),nullable=False),
    sa.Column('item_id',sa.String(36),sa.ForeignKey('consumable_items.id',ondelete='NO ACTION'),nullable=False),
    sa.Column('movement_type',sa.String(32),nullable=False),sa.Column('quantity',sa.Numeric(18,2),nullable=False),
    sa.Column('occurred_on',sa.Date(),nullable=False),sa.Column('unit_cost',sa.Numeric(18,2)),
    sa.Column('supplier',sa.Unicode(160)),sa.Column('reference_no',sa.Unicode(128)),
    sa.Column('computer_id',sa.String(36),sa.ForeignKey('computer_assets.id',ondelete='NO ACTION')),
    sa.Column('department_id',sa.String(36),sa.ForeignKey('departments.id',ondelete='NO ACTION')),
    sa.Column('user_id',sa.String(36),sa.ForeignKey('users.id',ondelete='NO ACTION')),
    sa.Column('recipient_text',sa.Unicode(160)),sa.Column('purpose',sa.Unicode(300)),sa.Column('notes',sa.Unicode(1000)),
    sa.Column('item_name_snapshot',sa.Unicode(160),nullable=False),sa.Column('unit_snapshot',sa.Unicode(32),nullable=False),
    sa.Column('is_reversed',sa.Boolean,nullable=False),
    sa.Column('reversal_of_id',sa.String(36),sa.ForeignKey('consumable_movements.id',ondelete='NO ACTION')),
    indexes=(('ix_consumable_movements_item_date',('item_id','occurred_on')),('ix_consumable_movements_computer',('computer_id','occurred_on')),
             ('ix_consumable_movements_department',('department_id','occurred_on')),
             ('ix_consumable_movements_reversal',('reversal_of_id',))))

secure_memos = _extra_table('secure_memos',
    sa.Column('id',sa.String(36),primary_key=True),
    sa.Column('created_at',sqltype('utc'),nullable=False),sa.Column('updated_at',sqltype('utc'),nullable=False),
    sa.Column('created_by_user_id',sa.String(36),sa.ForeignKey('users.id',ondelete='NO ACTION'),nullable=False),
    sa.Column('updated_by_user_id',sa.String(36),sa.ForeignKey('users.id',ondelete='NO ACTION'),nullable=False),
    sa.Column('version',sa.Integer,nullable=False),sa.Column('is_archived',sa.Boolean,nullable=False),
    sa.Column('title',sa.Unicode(160),nullable=False),sa.Column('category',sa.String(32),nullable=False),
    sa.Column('system_address',sa.Unicode(1000)),sa.Column('username',sa.Unicode(256)),
    sa.Column('password_ciphertext',sa.UnicodeText()),sa.Column('tags',sa.Unicode(500)),
    sa.Column('notes',sa.UnicodeText()),
    indexes=(('ix_secure_memos_owner_archived',('created_by_user_id','is_archived','updated_at')),))

# Organization data owned by the portal.  EHR identifiers are kept in a
# separate mapping table so manually maintained departments, users and jobs
# remain first-class portal records.
job_positions = _extra_table('job_positions',
    sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('updated_at',sa.DateTime(),nullable=False),
    sa.Column('created_by_user_id',sa.String(36),sa.ForeignKey('users.id',ondelete='NO ACTION')),
    sa.Column('updated_by_user_id',sa.String(36),sa.ForeignKey('users.id',ondelete='NO ACTION')),
    sa.Column('version',sa.Integer,nullable=False),sa.Column('is_archived',sa.Boolean,nullable=False),
    sa.Column('title',sa.Unicode(160),nullable=False),sa.Column('is_enabled',sa.Boolean,nullable=False),
    constraints=(sa.UniqueConstraint('title',name='uq_job_positions_title'),),
    indexes=(('ix_job_positions_title',('title','is_archived')),))

user_job_assignments = _extra_table('user_job_assignments',
    sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('updated_at',sa.DateTime(),nullable=False),
    sa.Column('created_by_user_id',sa.String(36),sa.ForeignKey('users.id',ondelete='NO ACTION')),
    sa.Column('updated_by_user_id',sa.String(36),sa.ForeignKey('users.id',ondelete='NO ACTION')),
    sa.Column('user_id',sa.String(36),sa.ForeignKey('users.id',ondelete='NO ACTION'),nullable=False),
    sa.Column('position_id',sa.String(36),sa.ForeignKey('job_positions.id',ondelete='NO ACTION'),nullable=False),
    sa.Column('source_type',sa.String(32),nullable=False),
    constraints=(sa.UniqueConstraint('user_id','position_id',name='uq_user_job_assignments_user_position'),),
    indexes=(('ix_user_job_assignments_user',('user_id',)),('ix_user_job_assignments_position',('position_id',))))

organization_external_links = _extra_table('organization_external_links',
    sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('updated_at',sa.DateTime(),nullable=False),
    sa.Column('source_code',sa.String(32),nullable=False),sa.Column('entity_type',sa.String(32),nullable=False),
    sa.Column('external_key',sa.Unicode(256),nullable=False),sa.Column('local_id',sa.String(36),nullable=False),
    sa.Column('last_seen_at',sa.DateTime(),nullable=False),
    constraints=(sa.UniqueConstraint('source_code','entity_type','external_key',name='uq_organization_external_links_source_entity_key'),),
    indexes=(('ix_organization_external_links_local',('entity_type','local_id')),))

organization_sync_state = _extra_table('organization_sync_state',
    sa.Column('source_code',sa.String(32),primary_key=True),sa.Column('first_success_at',sa.DateTime()),
    sa.Column('last_success_at',sa.DateTime()),sa.Column('last_attempt_at',sa.DateTime()),
    sa.Column('last_status',sa.String(32),nullable=False),sa.Column('last_message',sa.Unicode(1000)),
    sa.Column('updated_at',sa.DateTime(),nullable=False))

organization_sync_runs = _extra_table('organization_sync_runs',
    sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('completed_at',sa.DateTime()),
    sa.Column('source_code',sa.String(32),nullable=False),sa.Column('trigger_type',sa.String(32),nullable=False),
    sa.Column('trigger_key',sa.String(128),nullable=False),sa.Column('actor_user_id',sa.String(36),sa.ForeignKey('users.id',ondelete='NO ACTION')),
    sa.Column('status',sa.String(32),nullable=False),sa.Column('message',sa.Unicode(1000)),sa.Column('summary_json',sa.UnicodeText()),
    constraints=(sa.UniqueConstraint('source_code','trigger_key',name='uq_organization_sync_runs_source_trigger'),),
    indexes=(('ix_organization_sync_runs_created',('source_code','created_at')),))

quick_links = _extra_table('quick_links',
    sa.Column('id',sa.String(36),primary_key=True),
    sa.Column('created_at',sqltype('utc'),nullable=False),sa.Column('updated_at',sqltype('utc'),nullable=False),
    sa.Column('created_by_user_id',sa.String(36),sa.ForeignKey('users.id',ondelete='NO ACTION')),
    sa.Column('updated_by_user_id',sa.String(36),sa.ForeignKey('users.id',ondelete='NO ACTION')),
    sa.Column('version',sa.Integer,nullable=False),sa.Column('is_archived',sa.Boolean,nullable=False),
    sa.Column('title',sa.Unicode(120),nullable=False),sa.Column('url',sa.Unicode(1000),nullable=False),
    sa.Column('icon_text',sa.Unicode(16)),sa.Column('description',sa.Unicode(300)),
    sa.Column('link_category',sa.String(32),nullable=False),sa.Column('is_enabled',sa.Boolean,nullable=False),
    sa.Column('sort_order',sa.Integer,nullable=False),
    indexes=(('ix_quick_links_category_enabled',('link_category','is_enabled','sort_order')),))


def config_path():
    """Return the explicit deployment config, or the repository-local fallback."""
    configured = os.getenv('IT_PORTAL_CONFIG_FILE', '').strip()
    return Path(configured).expanduser().resolve() if configured else ROOT / 'business.local.json'


def settings():
    p = config_path()
    result = json.loads(p.read_text(encoding='utf-8-sig')) if p.exists() else {}
    result.setdefault('data_dir', str(ROOT / 'data' / 'business'))
    result.setdefault('monitor_url', 'https://monitor.example.com/')
    result.setdefault('log_retention_days',90)
    result.setdefault('audit_retention_days',180)
    result.setdefault('notification_retention_days',180)
    return result


def database_url(config, use_environment=True):
    if use_environment and os.getenv('IT_PORTAL_DATABASE_URL'):
        return os.environ['IT_PORTAL_DATABASE_URL']
    if config.get('database'):
        d = config['database']
        engine = d.get('engine', 'mssql')
        if engine not in ('mssql', 'mysql'):
            raise ValueError('database.engine must be mssql or mysql')
        query = {'driver': d.get('driver', 'ODBC Driver 18 for SQL Server'), 'Encrypt': 'yes', 'TrustServerCertificate': 'yes' if d.get('trust_server_certificate', False) else 'no'} if engine == 'mssql' else {'charset': 'utf8mb4'}
        socket_path = d.get('unix_socket') if engine == 'mysql' else None
        if socket_path:
            query['unix_socket'] = socket_path
        port = None if socket_path and not d.get('host') else int(d.get('port', 1433 if engine == 'mssql' else 3306))
        return URL.create('mssql+pyodbc' if engine == 'mssql' else 'mysql+pymysql',
                          username=d.get('username'), password=d.get('password'),
                          host=d.get('host') or None, port=port,
                          database=d.get('name', 'itPortal'), query=query)
    folder = Path(config['data_dir'])
    folder.mkdir(parents=True, exist_ok=True)
    return 'sqlite:///' + (folder / 'business.db').as_posix()


def make_engine(url):
    opts = {'pool_pre_ping': True, 'hide_parameters': True}
    if str(url).startswith('sqlite'):
        opts['connect_args'] = {'check_same_thread': False, 'timeout': 30}
    elif str(url).startswith('mysql'):
        # MySQL commonly closes idle connections before a long-running portal
        # process does. Recycling avoids exposing stale sockets to requests.
        opts['pool_recycle'] = 1800
    engine = sa.create_engine(url, **opts)
    if engine.dialect.name == 'sqlite':
        @sa.event.listens_for(engine, 'connect')
        def configure(dbapi_connection, _):
            dbapi_connection.execute('PRAGMA foreign_keys=ON')
            dbapi_connection.execute('PRAGMA journal_mode=WAL')
    return engine


def insert_row(conn, name, values, actor=None):
    """Common metadata only; no implicit business field values."""
    table = TABLES[name]
    now = utcnow()
    data = dict(values)
    defaults = {'id': uid(), 'created_at': now, 'updated_at': now,
                'created_by_user_id': actor, 'updated_by_user_id': actor,
                'version': 1, 'is_archived': False}
    for k, v in defaults.items():
        if k in table.c and k not in data:
            data[k] = v
    conn.execute(table.insert().values(**data))
    return dict(conn.execute(sa.select(table).where(table.c[table.primary_key.columns.keys()[0]] == data[table.primary_key.columns.keys()[0]])).mappings().one())


def row(conn, name, key):
    table = TABLES[name]
    return conn.execute(sa.select(table).where(table.c[table.primary_key.columns.keys()[0]] == key)).mappings().first()


def jsonable(value):
    if isinstance(value, dict) or isinstance(value, sa.engine.RowMapping):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat(timespec='milliseconds') + 'Z'
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return value
