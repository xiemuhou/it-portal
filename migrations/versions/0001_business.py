"""Initial database-backed portal schema. Frozen to the reviewed v0.2 schema."""
from pathlib import Path
import json
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mssql,mysql

revision='0001_business'
down_revision=None
branch_labels=None
depends_on=None


def initial_metadata():
    # Frozen copy: later application schema edits must not rewrite revision 0001.
    specs=json.loads((Path(__file__).parent/'0001_schema.json').read_text(encoding='utf-8'))
    meta=sa.MetaData()
    def kind(k):
        if k=='id':return sa.String(36)
        if k.startswith('a') and k[1:].isdigit():return sa.String(int(k[1:]))
        if k.startswith('u') and k[1:].isdigit():return sa.Unicode(int(k[1:]))
        return {'utc':sa.DateTime().with_variant(mssql.DATETIME2(precision=3),'mssql').with_variant(mysql.DATETIME(fsp=3),'mysql'),
            'date':sa.Date(),'bool':sa.Boolean(),'int':sa.Integer(),'bigint':sa.BigInteger(),'text':sa.UnicodeText(),'json':sa.UnicodeText(),
            'decimal18_2':sa.Numeric(18,2),'decimal12_3':sa.Numeric(12,3)}[k]
    for spec in specs:
        if spec['phase']!='V1':continue
        cols=[]
        for f in spec['effective_fields']:
            deferred=f['ref']=='users.id' and f['name'] in ('created_by_user_id','updated_by_user_id','archived_by_user_id','verified_by_user_id')
            args=[sa.ForeignKey(f['ref'],name=f'fk_{spec["name"]}_{f["name"]}',ondelete='NO ACTION',use_alter=deferred)] if f['ref'] else []
            cols.append(sa.Column(f['name'],kind(f['type']),*args,primary_key=f['name']==spec['pk'],nullable=False if f['name']==spec['pk'] else f['nullable']))
        constraints=[sa.PrimaryKeyConstraint(spec['pk'],name='pk_'+spec['name'])]
        for i,expr in enumerate(spec['unique'].split(';')):
            if expr.strip():constraints.append(sa.UniqueConstraint(*[c.strip() for c in expr.split(',')],name=f'uq_{spec["name"]}_{i}'))
        t=sa.Table(spec['name'],meta,*cols,*constraints,mysql_charset='utf8mb4')
        for i,expr in enumerate(spec['indexes'].split(';')):
            if expr.strip():sa.Index(f'ix_{spec["name"]}_{i}',*[t.c[c.strip()] for c in expr.split(',')])
    return meta


def upgrade():initial_metadata().create_all(op.get_bind())


def downgrade():
    raise RuntimeError('Initial schema downgrade would delete business data. Restore a verified backup instead.')
